"""
    ESSArch is an open source archiving and digital preservation system

    ESSArch
    Copyright (C) 2005-2019 ES Solutions AB

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program. If not, see <https://www.gnu.org/licenses/>.

    Contact information:
    Web - http://www.essolutions.se
    Email - essarch@essolutions.se
"""

import logging
import os
import shutil
import tarfile
import tempfile
import zipfile

from celery.exceptions import Ignore
from celery.result import allow_join_result
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import F
from django.utils import timezone

# noinspection PyUnresolvedReferences
from ESSArch_Core import tasks  # noqa
from ESSArch_Core.auth.models import Notification
from ESSArch_Core.config.celery import app
from ESSArch_Core.configuration.models import Path
from ESSArch_Core.fixity.checksum import calculate_checksum
from ESSArch_Core.ip.models import (
    MESSAGE_DIGEST_ALGORITHM_CHOICES_DICT,
    InformationPackage,
    Workarea,
)
from ESSArch_Core.storage.exceptions import (
    TapeDriveLockedError,
    TapeMountedAndLockedByOtherError,
    TapeMountedError,
    TapeUnmountedError,
)
from ESSArch_Core.storage.models import (
    Robot,
    RobotQueue,
    StorageObject,
    TapeDrive,
)
from ESSArch_Core.util import (
    creation_date,
    delete_path,
    find_destination,
    run_shell_command,
    timestamp_to_datetime,
)
from ESSArch_Core.WorkflowEngine.models import ProcessTask

User = get_user_model()
logger = logging.getLogger('essarch')


@app.task(bind=True)
@transaction.atomic
def ReceiveDir(self):
    def _get_workarea_path():
        ip = InformationPackage.objects.get(pk=self.ip)
        workarea = Path.objects.get(entity='ingest_workarea').value
        username = User.objects.get(pk=self.responsible).username
        workarea_user = os.path.join(workarea, username)
        return os.path.join(workarea_user, ip.object_identifier_value)

    ip = InformationPackage.objects.get(pk=self.ip)
    objpath = ip.object_path
    workarea_path = _get_workarea_path()

    shutil.copytree(objpath, workarea_path)
    ip.object_path = workarea_path
    ip.save()
    Workarea.objects.create(ip=ip, user_id=self.responsible, type=Workarea.INGEST, read_only=False)

    self.create_success_event("Received IP")


@app.task(bind=True, event_type=20100)
@transaction.atomic
def ReceiveSIP(self, purpose=None, delete_sip=False):
    logger = logging.getLogger('essarch.workflow.tasks.ReceiveSIP')
    logger.debug('Receiving SIP')
    ip = self.get_information_package()
    algorithm = ip.get_checksum_algorithm()
    container = ip.object_path
    objid, container_type = os.path.splitext(os.path.basename(container))
    container_type = container_type.lower()
    xml = ip.package_mets_path
    if os.path.exists(xml):
        ip.package_mets_create_date = timestamp_to_datetime(creation_date(xml)).isoformat()
        ip.package_mets_size = os.path.getsize(xml)
        ip.package_mets_digest_algorithm = MESSAGE_DIGEST_ALGORITHM_CHOICES_DICT[algorithm.upper()]
        ip.package_mets_digest = calculate_checksum(xml, algorithm=algorithm)

    ip.object_path = os.path.join(ip.policy.ingest_path.value, ip.object_identifier_value)
    ip.save()

    sip_dst_path, sip_dst_name = find_destination('sip', ip.get_structure(), ip.object_path)
    if sip_dst_path is None:
        sip_dst_path, sip_dst_name = find_destination('content', ip.get_structure(), ip.object_path)

    if sip_dst_name:
        sip_dst_name, = self.parse_params(sip_dst_name)
    sip_dst = os.path.join(sip_dst_path, sip_dst_name)

    if ip.policy.receive_extract_sip:
        # remove any existing directory from previous attempts
        delete_path(sip_dst)

        temp = Path.objects.get(entity='temp').value
        with tempfile.TemporaryDirectory(dir=temp) as tmpdir:
            logger.debug('Extracting {} to {}'.format(container, tmpdir))
            if container_type == '.tar':
                try:
                    with tarfile.open(container) as tar:
                        root_member_name = tar.getnames()[0]
                        def is_within_directory(directory, target):
                            
                            abs_directory = os.path.abspath(directory)
                            abs_target = os.path.abspath(target)
                        
                            prefix = os.path.commonprefix([abs_directory, abs_target])
                            
                            return prefix == abs_directory
                        
                        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
                        
                            for member in tar.getmembers():
                                member_path = os.path.join(path, member.name)
                                if not is_within_directory(path, member_path):
                                    raise Exception("Attempted Path Traversal in Tar File")
                        
                            tar.extractall(path, members, numeric_owner=numeric_owner) 
                            
                        
                        safe_extract(tar, tmpdir)
                except NotADirectoryError as e:
                    logger.warning('Problem to extract tarfile: {} (trying to run shell tar extract), error: {}\
'.format(container, e))
                    run_shell_command(['tar', 'xvf', container], tmpdir)
            elif container_type == '.zip':
                with zipfile.ZipFile(container) as zipf:
                    os.path.altsep = getattr(settings, 'OS_PATH_ALTSEP', None)
                    root_member_name = zipf.namelist()[0]
                    zipf.extractall(tmpdir)
            else:
                raise ValueError('Invalid container type: {}'.format(container))

            sip_dst = os.path.join(sip_dst, '')
            os.makedirs(sip_dst)

            tmpsrc = tmpdir
            if len(os.listdir(tmpdir)) == 1 and os.listdir(tmpdir)[0] == root_member_name:
                new_tmpsrc = os.path.join(tmpdir, root_member_name)
                if os.path.isdir(new_tmpsrc):
                    tmpsrc = new_tmpsrc

            logger.debug('Moving content of {} to {}'.format(tmpsrc, sip_dst))

            for f in os.listdir(tmpsrc):
                shutil.move(os.path.join(tmpsrc, f), sip_dst)

            logger.debug('Deleting {}'.format(tmpdir))
    else:
        logger.debug('Copying {} to {}'.format(container, sip_dst))
        shutil.copy2(container, sip_dst)

    ip.sip_path = os.path.relpath(sip_dst, ip.object_path)
    ip.save()
    self.create_success_event("Received SIP")
    return sip_dst


@app.task(bind=True, event_type=30710)
def ReceiveAIP(self, workarea):
    workarea = Workarea.objects.prefetch_related('ip').get(pk=workarea)
    ip = workarea.ip

    ip.state = 'Receiving'
    ip.save(update_fields=['state'])

    ingest = ip.policy.ingest_path
    dst = os.path.join(ingest.value, ip.object_identifier_value)

    shutil.copytree(ip.object_path, dst)

    ip.object_path = dst
    ip.save(update_fields=['object_path'])


@app.task(bind=True)
def AccessAIP(self, aip, storage_object=None, tar=True, extracted=False, new=False, package_xml=False,
              aic_xml=False, object_identifier_value="", dst=None):
    aip = InformationPackage.objects.get(pk=aip)
    responsible = User.objects.get(pk=self.responsible)

    # if it is a received IP, i.e. from ingest and not from storage,
    # then we read it directly from disk and move it to the ingest workarea
    if aip.state == 'Received':
        if not extracted and not new:
            raise ValueError('An IP must be extracted when transferred to ingest workarea')

        if new:
            # Create new generation of the IP

            old_aip = aip.pk
            new_aip = aip.create_new_generation('Ingest Workarea', responsible, object_identifier_value)
            aip = InformationPackage.objects.get(pk=old_aip)
        else:
            new_aip = aip

        workarea = Path.objects.get(entity='ingest_workarea').value
        workarea_user = os.path.join(workarea, responsible.username)
        dst_dir = os.path.join(workarea_user, new_aip.object_identifier_value, )

        shutil.copytree(aip.object_path, dst_dir)

        workarea_obj = Workarea.objects.create(
            ip=new_aip, user_id=self.responsible, type=Workarea.INGEST, read_only=not new
        )
        Notification.objects.create(
            message="%s is now in workspace" % new_aip.object_identifier_value,
            level=logging.INFO, user_id=self.responsible, refresh=True
        )

        if new:
            new_aip.object_path = dst_dir
            new_aip.save(update_fields=['object_path'])

        return str(workarea_obj.pk)

    if storage_object is not None:
        storage_object = StorageObject.objects.get(pk=storage_object)
    else:
        storage_object = aip.get_fastest_readable_storage_object()

    aip.access(storage_object, self.get_processtask(), dst=dst)


@app.task(bind=True, track=False)
def PollRobotQueue(self):
    force_entries = RobotQueue.objects.filter(
        req_type=30, status__in=[0, 2]
    ).select_related('storage_medium').order_by('-status', 'posted')

    non_force_entries = RobotQueue.objects.filter(
        status__in=[0, 2]
    ).exclude(req_type=30).select_related('storage_medium').order_by('-status', '-req_type', 'posted')[:5]

    entries = list(force_entries) + list(non_force_entries)

    if not len(entries):
        raise Ignore()

    for entry in entries:
        entry.status = 2
        entry.save(update_fields=['status'])

        medium = entry.storage_medium

        if entry.req_type == 10:  # mount
            if medium.tape_drive is not None:  # already mounted
                if hasattr(entry, 'io_queue_entry'):  # mounting for read or write
                    if medium.tape_drive.io_queue_entry != entry.io_queue_entry:
                        raise TapeMountedAndLockedByOtherError(
                            "Tape already mounted and locked by '%s'" % medium.tape_drive.io_queue_entry
                        )

                    entry.delete()

                raise TapeMountedError("Tape already mounted")

            drive = entry.tape_drive

            if drive is None:
                free_drive = TapeDrive.objects.filter(
                    status=20, storage_medium__isnull=True, io_queue_entry__isnull=True, locked=False,
                ).order_by('num_of_mounts').first()

                if free_drive is None:
                    raise ValueError('No tape drive available')

                drive = free_drive

            free_robot = Robot.objects.filter(robot_queue__isnull=True).first()

            if free_robot is None:
                raise ValueError('No robot available')

            entry.robot = free_robot
            entry.status = 5
            entry.save(update_fields=['robot', 'status'])

            with allow_join_result():

                try:
                    ProcessTask.objects.create(
                        name="ESSArch_Core.tasks.MountTape",
                        params={
                            'medium': medium.pk,
                            'drive': drive.pk,
                        }
                    ).run().get()
                except TapeMountedError:
                    entry.delete()
                    raise
                except BaseException:
                    entry.status = 100
                    raise
                else:
                    medium.tape_drive = drive
                    medium.save(update_fields=['tape_drive'])
                    entry.delete()
                finally:
                    entry.robot = None
                    entry.save(update_fields=['robot', 'status'])

        elif entry.req_type in [20, 30]:  # unmount
            if medium.tape_drive is None:  # already unmounted
                entry.delete()
                raise TapeUnmountedError("Tape already unmounted")

            if medium.tape_drive.locked:
                if entry.req_type == 20:
                    raise TapeDriveLockedError("Tape locked")

            free_robot = Robot.objects.filter(robot_queue__isnull=True).first()

            if free_robot is None:
                raise ValueError('No robot available')

            entry.robot = free_robot
            entry.status = 5
            entry.save(update_fields=['robot', 'status'])

            with allow_join_result():
                try:
                    ProcessTask.objects.create(
                        name="ESSArch_Core.tasks.UnmountTape",
                        params={
                            'drive': medium.tape_drive.pk,
                        }
                    ).run().get()
                except TapeUnmountedError:
                    entry.delete()
                    raise
                except BaseException:
                    entry.status = 100
                    raise
                else:
                    medium.tape_drive = None
                    medium.save(update_fields=['tape_drive'])
                    entry.delete()
                finally:
                    entry.robot = None
                    entry.save(update_fields=['robot', 'status'])


@app.task(bind=True, track=False)
def UnmountIdleDrives(self):
    idle_drives = TapeDrive.objects.filter(
        status=20, storage_medium__isnull=False,
        last_change__lte=timezone.now() - F('idle_time'),
        locked=False,
    )

    if not idle_drives.exists():
        raise Ignore()

    for drive in idle_drives.iterator():
        robot_queue_entry_exists = RobotQueue.objects.filter(
            storage_medium=drive.storage_medium, req_type=20, status__in=[0, 2]
        ).exists()
        if not robot_queue_entry_exists:
            RobotQueue.objects.create(
                user=User.objects.get(username='system'),
                storage_medium=drive.storage_medium,
                req_type=20, status=0,
            )
