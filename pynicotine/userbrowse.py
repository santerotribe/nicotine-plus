# SPDX-FileCopyrightText: 2020-2026 Nicotine+ Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import hashlib
import json
import os
import time

from collections import Counter
from concurrent.futures import Future, ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import chain

from pynicotine.config import config
from pynicotine.core import core
from pynicotine.events import events
from pynicotine.logfacility import log
from pynicotine.shares import PermissionLevel
from pynicotine.slskmessages import (
    AddAllowedResponse,
    ConnectionType,
    FileAttribute,
    FileAttributes,
    Login,
    MessageParser,
    RemoveAllowedResponse,
    SharedFile,
    SharedFileListRequest,
    SharedFileListResponse,
    UploadQueueNotification,
    UserStatus
)
from pynicotine.utils import (
    encode_path,
    human_size,
    humanize,
    safe_path_join
)


class TaskType(StrEnum):
    PROCESS = "process"
    THREAD = "thread"


_AUDIO_FORMATS = {
    "flac", "mp3", "wav", "aiff", "aif", "m4a", "ogg", "opus",
    "wma", "ape", "wv", "alac",
}
_LOSSLESS_FORMATS = {"flac", "wav", "aiff", "aif", "ape", "wv", "alac"}


def _folder_info(folder: str, files: list[SharedFile]) -> dict:
    """Aggregate one share folder: tracks, bytes, audio formats, playing time.

    "files" and "size" describe everything in the folder, covers included.
    "audio_files", "audio_formats" and "lossless" describe only playable audio,
    so a folder of eight FLACs and two cover JPEGs is 100% lossless, not 80%.
    """

    size = 0
    duration = 0
    audio_files = 0
    lossless = 0
    formats: Counter[str] = Counter()
    fingerprint: list[str] = []

    for file in files:
        try:
            size += int(file.size or 0)
        except (TypeError, ValueError):
            pass

        name = str(getattr(file, "path", "") or "").rsplit("\\", 1)[-1]
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""

        if extension in _AUDIO_FORMATS:
            audio_files += 1
            formats[extension] += 1
            fingerprint.append(f"{name}\t{getattr(file, 'size', 0) or 0}")

            if extension in _LOSSLESS_FORMATS:
                lossless += 1

            attributes = getattr(file, "attributes", None)
            length = getattr(attributes, "length", None) if attributes else None

            try:
                length = int(length or 0)
            except (TypeError, ValueError):
                length = 0

            if length > 0:
                duration += length

    return {
        "name": folder,
        "files": len(files),
        "size": size,
        "audio_files": audio_files,
        "audio_formats": dict(formats.most_common(4)),
        "lossless": lossless,
        "duration": int(duration),
        # Names + sizes of the audio only: catches a swap that keeps the count.
        "digest": hashlib.sha1(
            "\n".join(sorted(fingerprint)).encode("utf-8", "replace")
        ).hexdigest()[:16],
    }


def _all_folder_names(browsed_user: "BrowsedUser") -> list[str]:
    """Public and private shares at once: a peer can have both."""

    return list(dict.fromkeys([
        *browsed_user.public_folders,
        *browsed_user.private_folders,
    ]))


def _folder_files(browsed_user: "BrowsedUser", folder: str) -> list[SharedFile]:
    return [
        *(browsed_user.public_folders.get(folder) or []),
        *(browsed_user.private_folders.get(folder) or []),
    ]


@dataclass(slots=True, eq=False)
class BrowsedUser:
    username: str
    num_folders: int | None = None
    num_files: int | None = None
    shared_size: int | None = None
    public_folders: dict[str, list[SharedFile]] = field(default_factory=dict)
    private_folders: dict[str, list[SharedFile]] = field(default_factory=dict)
    saving: bool = False

    def clear(self) -> None:

        self.num_folders = self.num_files = self.shared_size = None
        self.public_folders.clear()
        self.private_folders.clear()


class UserBrowse:
    __slots__ = ("users", "user_shares_folder", "_task_pools", "_browse_timing")

    def __init__(self):

        self.users = {}
        self._browse_timing: dict[str, dict] = {}
        self.user_shares_folder = os.path.join(config.data_folder_path, "usershares")
        self._task_pools: dict[TaskType, ProcessPoolExecutor | ThreadPoolExecutor] = {}

        for event_name, callback in (
            ("peer-connection-closed", self._peer_connection_error),
            ("peer-connection-error", self._peer_connection_error),
            ("quit", self._quit),
            ("server-login", self._server_login),
            ("shared-file-list-response", self._shared_file_list_response),
            ("shared-file-list-save-failed", self._shared_file_list_save_failed),
            ("shared-file-list-saved", self._shared_file_list_saved)
        ):
            events.connect(event_name, callback)

    def _quit(self) -> None:

        for pool in self._task_pools.values():
            pool.shutdown(cancel_futures=True)

        self._task_pools.clear()
        self.remove_all_users()

    def _server_login(self, msg: Login) -> None:

        if not msg.success:
            return

        for username in self.users:
            core.users.watch_user(username, context="userbrowse")  # Get notified of user status

    def browse_user(self, username: str, path=None, new_request=False, switch_page=True) -> None:
        """Browse a user's shares."""

        if not username:
            return

        local_username = core.users.login_username or config.sections["server"]["login"]

        if username == local_username:
            self.browse_local_shares(path, new_request=new_request, switch_page=switch_page)
            return

        new_request = self._show_user(username, path=path, new_request=new_request, switch_page=switch_page)

        if new_request:
            self.request_user_shares(username)

    def browse_local_shares(
        self, path: str | None = None, permission_level: PermissionLevel | None = None,
        new_request: bool = False, switch_page: bool = True
    ) -> None:
        """Browse your own shares."""

        username = core.users.login_username or config.sections["server"]["login"]

        if not username:
            core.setup()
            return

        new_request = self._show_user(username, path=path, new_request=new_request, switch_page=switch_page)

        if not new_request:
            return

        if not permission_level:
            # Check our own permission level, and show relevant shares for it
            current_permission_level, _reason = core.shares.check_user_permission(username)
        else:
            current_permission_level = permission_level

        msg = core.shares.compressed_shares.get(current_permission_level)

        def finish_task(future: Future) -> None:
            msg = future.result()
            events.emit_main_thread("shared-file-list-response", msg)

        pool = self._create_task_pool(TaskType.THREAD)
        future = pool.submit(self._run_task_parse_local, username, msg)
        future.add_done_callback(finish_task)

    def remove_user(self, username: str) -> None:

        if username not in self.users:
            return

        del self.users[username]
        core.send_message_to_network_thread(RemoveAllowedResponse(SharedFileListResponse, username))
        core.users.unwatch_user(username, context="userbrowse")
        events.emit("user-browse-remove-user", username)

    def remove_all_users(self) -> None:
        for username in self.users.copy():
            self.remove_user(username)

    def user_summary(self, username: str) -> dict | None:
        """Small snapshot of a browsed user, shared by any front end."""

        browsed_user = self.users.get(username)

        if browsed_user is None:
            return None

        folders = _all_folder_names(browsed_user)
        files = sum(len(_folder_files(browsed_user, folder)) for folder in folders)

        return {
            "username": username,
            "folders": len(folders) if folders else (browsed_user.num_folders or 0),
            "files": files if folders else (browsed_user.num_files or 0),
            "shared_size": browsed_user.shared_size or 0,
            "messages": self._browse_timing.get(username, {}).get("messages", 0),
        }

    def folder_page(self, username: str, offset: int = 0, limit: int = 200) -> dict | None:
        """Page through a user's folders with what each one holds.

        The native shelf sorts and filters bins by size, format mix and length,
        so the aggregate is computed here from the share already in memory
        instead of making the front end fetch every folder's files.
        """

        browsed_user = self.users.get(username)

        if browsed_user is None:
            return None

        # One snapshot for the whole page: a browse that clears or appends while
        # this runs must not yield an old total with zeroed rows.
        snapshot: dict[str, list] = {}

        for folder, files in chain(
            browsed_user.public_folders.items(),
            browsed_user.private_folders.items(),
        ):
            snapshot.setdefault(folder, []).extend(files)

        folders = list(snapshot)
        total = len(folders)
        offset = max(0, int(offset))
        limit = max(1, int(limit))
        page = folders[offset:offset + limit]
        details = [_folder_info(folder, snapshot.get(folder, [])) for folder in page]

        return {"username": username, "total": total, "offset": offset,
                "limit": limit, "folders": details}

    def file_page(self, username: str, folder_path: str = "", offset: int = 0,
                  limit: int = 500) -> dict | None:
        """Page through one folder's files. The unit a native list view needs."""

        browsed_user = self.users.get(username)

        if browsed_user is None:
            return None

        files = _folder_files(browsed_user, folder_path)
        offset = max(0, int(offset))
        limit = max(1, int(limit))

        return {
            "username": username,
            "folder": folder_path,
            "total": len(files),
            "offset": offset,
            "limit": limit,
            "files": files[offset:offset + limit],
        }

    def request_user_shares(self, username: str) -> None:

        if core.users.login_status == UserStatus.OFFLINE:
            events.emit("shared-file-list-failed", username, is_offline=True)
            return

        self._browse_timing[username] = {
            "started": time.monotonic(),
            "messages": 0,
            "folders": 0,
            "files": 0,
        }
        core.send_message_to_network_thread(AddAllowedResponse(SharedFileListResponse, username))
        core.send_message_to_peer(username, SharedFileListRequest())

    def create_user_shares_folder(self) -> str | None:

        folder_path_encoded = encode_path(self.user_shares_folder)

        try:
            if not os.path.isdir(folder_path_encoded):
                os.makedirs(folder_path_encoded)

        except Exception as error:
            log.add(_("Cannot create folder %(path)s: %(error)s"),
                    {"path": self.user_shares_folder, "error": error})
            return None

        return self.user_shares_folder

    def load_shares_list_from_disk(self, file_path: str) -> None:

        username = os.path.basename(file_path)
        self._show_user(username, new_request=True)

        def finish_task(future: Future) -> None:

            try:
                msg = future.result()

            except Exception as error:
                events.emit_main_thread("shared-file-list-failed", username, disk_error=error)
                return

            events.emit_main_thread("shared-file-list-response", msg)

        pool = self._create_task_pool(TaskType.PROCESS)
        future = pool.submit(self._run_task_parse_disk, username, file_path)
        future.add_done_callback(finish_task)

    def save_shares_list_to_disk(self, username: str) -> None:

        browsed_user = self.users.get(username)

        if browsed_user is None:
            return

        if browsed_user.saving:
            return

        file_path = safe_path_join(self.user_shares_folder, username)
        browsed_user.saving = True

        def finish_task(future: Future) -> None:

            error = future.exception()

            if error is not None:
                events.emit_main_thread("shared-file-list-save-failed", username, file_path, error)
                return

            events.emit_main_thread("shared-file-list-saved", username, file_path)

        pool = self._create_task_pool(TaskType.THREAD)
        future = pool.submit(
            self._run_task_save_disk, file_path, browsed_user.public_folders, browsed_user.private_folders
        )
        future.add_done_callback(finish_task)

    def iter_matching_folders(self, requested_folder_path: str, browsed_user: BrowsedUser, recurse: bool = False):

        for folders in (browsed_user.public_folders, browsed_user.private_folders):
            for folder_path, files in folders.items():
                if (requested_folder_path != folder_path
                        and not (recurse and folder_path.startswith(f"{requested_folder_path}\\"))):
                    continue

                yield folder_path, files

                if not recurse:
                    return

    def download_file(
        self, username: str, folder_path: str, file_data, download_folder_path: str | None = None
    ) -> None:

        core.downloads.enqueue_download(
            username, virtual_path="\\".join([folder_path, file_data.path]),
            folder_path=download_folder_path, size=file_data.size, file_attributes=file_data.attributes
        )

    def download_folder(
        self, username: str, requested_folder_path, download_folder_path: str | None = None,
        recurse: bool = False, check_num_files: bool = True
    ) -> None:

        browsed_user = self.users.get(username)

        if browsed_user is None:
            return

        num_files = 0

        for folder_path, files in self.iter_matching_folders(
            requested_folder_path, browsed_user=browsed_user, recurse=recurse
        ):
            num_files += len(files)

        if check_num_files and num_files > 1000:
            # Large folder, ask user for confirmation before downloading
            check_num_files = False
            events.emit(
                "download-large-folder", username, requested_folder_path, num_files,
                self.download_folder, (
                    username, requested_folder_path, download_folder_path, recurse, check_num_files
                )
            )
            return

        for folder_path, files in self.iter_matching_folders(
            requested_folder_path, browsed_user=browsed_user, recurse=recurse
        ):
            # Get final download destination
            destination_folder_path = core.downloads.get_folder_destination(
                username, folder_path, root_folder_path=requested_folder_path,
                download_folder_path=download_folder_path)

            for file_data in files:
                core.downloads.enqueue_download(
                    username, virtual_path="\\".join([folder_path, file_data.path]),
                    folder_path=destination_folder_path, size=file_data.size,
                    file_attributes=file_data.attributes
                )

    def upload_file(self, username: str, folder_path: str, basename) -> None:
        core.uploads.enqueue_upload(username, virtual_path="\\".join([folder_path, basename]))

    def upload_folder(
        self, username: str, requested_folder_path: str, local_browsed_user: BrowsedUser, recurse: bool = False
    ) -> None:

        if not requested_folder_path or not username:
            return

        for folder_path, files in self.iter_matching_folders(
            requested_folder_path, browsed_user=local_browsed_user, recurse=recurse
        ):
            for file_data in files:
                core.uploads.enqueue_upload(username, virtual_path="\\".join([folder_path, file_data.path]))

    def send_upload_attempt_notification(self, username: str) -> None:
        """Send notification to user when attempting to initiate upload from
        our end."""

        core.send_message_to_peer(username, UploadQueueNotification())

    def show_user_statistics(self, username: str) -> None:

        browsed_user = self.users.get(username)

        if browsed_user is None:
            return

        log.add(_("User %(user)s is sharing %(num_files)s files totaling %(shared_size)s across "
                  "%(num_folders)s folders"), {
            "user": username,
            "num_files": humanize(browsed_user.num_files or 0),
            "shared_size": human_size(browsed_user.shared_size or 0),
            "num_folders": humanize(browsed_user.num_folders or 0)
        }, title=_("User Statistics"))

    @staticmethod
    def get_soulseek_url(username: str, path: str) -> str:

        import urllib.parse
        path = path.replace("\\", "/")
        return "slsk://" + urllib.parse.quote(f"{username}/{path}")

    def open_soulseek_url(self, url: str) -> None:

        if not url.startswith("slsk://"):
            return

        import urllib.parse

        url = urllib.parse.unquote(url.replace("slsk://", "", 1))
        username, _separator, file_path = url.partition("/")
        file_path = file_path.replace("/", "\\")

        self.browse_user(username, path=file_path)

    def _create_task_pool(self, task_type: TaskType) -> ProcessPoolExecutor | ThreadPoolExecutor:

        pool = self._task_pools.get(task_type)

        if pool is None:
            if task_type == TaskType.PROCESS:
                pool = self._task_pools[task_type] = ProcessPoolExecutor(max_workers=1, max_tasks_per_child=1)
            else:
                pool = self._task_pools[task_type] = ThreadPoolExecutor(max_workers=1)

        return pool

    def _show_user(
        self, username: str, path: str | None = None, new_request: bool = False, switch_page: bool = True
    ) -> None:

        browsed_user = self.users.get(username)

        if browsed_user is None:
            self.users[username] = BrowsedUser(username)
            new_request = True

        elif new_request:
            browsed_user.clear()

        if new_request:
            # Start the latency clock when the request is made, whether the list
            # comes from a peer or from our own shares on disk.
            self._browse_timing[username] = {
                "started": time.monotonic(), "messages": 0, "folders": 0, "files": 0
            }

        events.emit(
            "user-browse-show-user", username, path=path, new_request=new_request,
            switch_page=switch_page
        )
        core.users.watch_user(username, context="userbrowse")
        return new_request

    @staticmethod
    def _run_task_parse_local(username: str, msg: SharedFileListResponse) -> SharedFileListResponse:

        parser = MessageParser(memoryview(msg.pack()))
        unpacked_msg = msg.unpack(parser)
        unpacked_msg.username = username

        return unpacked_msg

    @staticmethod
    def _run_task_parse_disk(username: str, file_path: str) -> SharedFileListResponse:

        file_path_encoded = encode_path(file_path)
        msg = None

        try:
            # Try legacy format first
            import bz2

            with bz2.BZ2File(file_path_encoded) as file_handle:
                from pynicotine.shares import RestrictedUnpickler
                shares_list = RestrictedUnpickler(file_handle, encoding="utf-8").load()

        except Exception:
            # Try new format
            with open(file_path_encoded, encoding="utf-8") as file_handle:
                shares_list = json.load(file_handle)

        bitrate_key = str(FileAttribute.BITRATE)
        length_key = str(FileAttribute.LENGTH)
        vbr_key = str(FileAttribute.VBR)
        sample_rate_key = str(FileAttribute.SAMPLE_RATE)
        bit_depth_key = str(FileAttribute.BIT_DEPTH)

        for _folder_path, files in shares_list:
            for i, file_data in enumerate(files):
                code = file_data[0]

                if not isinstance(code, int):
                    code = 1

                basename = file_data[1]

                if not isinstance(basename, str):
                    raise TypeError(_("Invalid file name in shares"))

                size = file_data[2]

                if not isinstance(size, int):
                    raise TypeError(_("Invalid file size in shares"))

                attributes = file_data[4]

                if isinstance(attributes, dict):
                    bitrate = attributes.get(bitrate_key)
                    length = attributes.get(length_key)
                    vbr = attributes.get(vbr_key)
                    sample_rate = attributes.get(sample_rate_key)
                    bit_depth = attributes.get(bit_depth_key)
                else:
                    # Legacy attribute list format used for shares lists saved in Nicotine+ 3.2.2 and earlier
                    bitrate = length = vbr = sample_rate = bit_depth = None

                    if len(attributes) == 3:
                        attribute1, attribute2, attribute3 = attributes

                        if attribute3 in {0, 1}:
                            bitrate = attribute1
                            length = attribute2
                            vbr = attribute3

                        elif attribute3 > 1:
                            length = attribute1
                            sample_rate = attribute2
                            bit_depth = attribute3

                    elif len(attributes) == 2:
                        attribute1, attribute2 = attributes

                        if attribute2 in {0, 1}:
                            bitrate = attribute1
                            vbr = attribute2

                        elif attribute1 >= 8000 and attribute2 <= 64:
                            sample_rate = attribute1
                            bit_depth = attribute2

                        else:
                            bitrate = attribute1
                            length = attribute2

                files[i] = SharedFile(
                    code=code,
                    path=basename,
                    size=size,
                    extension=None,
                    attributes=FileAttributes(bitrate, length, vbr, sample_rate, bit_depth)
                )

        msg = SharedFileListResponse(public_folders=shares_list)
        msg.username = username

        return msg

    @staticmethod
    def _run_task_save_disk(
        file_path: str,
        public_folders: dict[str, list[SharedFile]], private_folders: dict[str, list[SharedFile]]
    ) -> None:

        folder_path_encoded = encode_path(os.path.dirname(file_path))

        if not os.path.isdir(folder_path_encoded):
            os.makedirs(folder_path_encoded)

        with open(encode_path(file_path), "w", encoding="utf-8") as file_handle:
            # Dump every folder to the file individually to avoid large memory usage
            json_encoder = json.JSONEncoder(
                check_circular=False, ensure_ascii=False, default=lambda x: x.serialize()
            )
            is_first_item = True

            file_handle.write("[")

            for folders in (public_folders, private_folders):
                for item in folders.items():
                    if is_first_item:
                        is_first_item = False
                    else:
                        file_handle.write(",\n")

                    file_handle.write(json_encoder.encode(item))

            file_handle.write("]")

    def _shared_file_list_saved(self, username, file_path):

        browsed_user = self.users.get(username)

        if browsed_user is not None:
            browsed_user.saving = False

        log.add(_("Saved list of shared files for user '%(user)s' to %(dir)s"), {
            "user": username,
            "dir": os.path.dirname(file_path)
        })

    def _shared_file_list_save_failed(self, username, file_path, error):

        browsed_user = self.users.get(username)

        if browsed_user is not None:
            browsed_user.saving = False

        log.add(_("Cannot save list of shared files to %(filename)s: %(error)s"), {
            "filename": file_path,
            "error": error
        })

    def _peer_connection_error(self, username: str, conn_type: ConnectionType, msgs, is_offline: bool = False) -> None:

        if not msgs:
            return

        if conn_type != ConnectionType.PEER:
            return

        for msg in msgs:
            if isinstance(msg, (SharedFileListRequest, SharedFileListResponse)):
                core.send_message_to_network_thread(RemoveAllowedResponse(SharedFileListResponse, username))
                events.emit("shared-file-list-failed", username, is_offline)
                break

    def _shared_file_list_response(self, msg: SharedFileListResponse) -> None:

        username = msg.username
        browsed_user = self.users.get(username)
        num_folders = len(msg.public_folders) + len(msg.private_folders)
        num_files = 0
        shared_size = 0

        for _folder_path, files in chain(msg.public_folders, msg.private_folders):
            for file_data in files:
                shared_size += file_data.size

            num_files += len(files)

        if browsed_user is not None:
            browsed_user.public_folders.update(msg.public_folders)
            browsed_user.private_folders.update(msg.private_folders)
            browsed_user.num_folders = num_folders
            browsed_user.num_files = num_files
            browsed_user.shared_size = shared_size

            # Browse latency split: how long the peer took to answer, and how
            # much data arrived per message. Used when tuning large libraries.
            timing = self._browse_timing.setdefault(
                username, {"started": time.monotonic(), "messages": 0, "folders": 0, "files": 0}
            )
            timing["messages"] += 1
            timing["folders"] = max(timing["folders"], num_folders)
            timing["files"] = max(timing["files"], num_files)
            elapsed = time.monotonic() - timing["started"]

            if timing["messages"] == 1 or elapsed >= 5:
                log.add(
                    "Browse: %(user)s answered in %(elapsed).2fs "
                    "(%(folders)s folders, %(files)s files, message %(messages)s)",
                    {"user": username, "elapsed": elapsed, "folders": num_folders,
                     "files": num_files, "messages": timing["messages"]}
                )
                timing["started"] = time.monotonic()

        core.send_message_to_network_thread(RemoveAllowedResponse(SharedFileListResponse, username))

        core.pluginhandler.user_stats_notification(username, stats={
            "avgspeed": None,
            "files": num_files,
            "dirs": num_folders,
            "shared_size": shared_size,
            "source": "peer"
        })
