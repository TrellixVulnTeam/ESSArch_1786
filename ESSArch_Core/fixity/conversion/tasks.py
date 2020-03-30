import os
from pathlib import PurePath

from glob2 import iglob

from ESSArch_Core.fixity.models import ConversionTool
from ESSArch_Core.ip.models import EventIP
from ESSArch_Core.util import in_directory
from ESSArch_Core.WorkflowEngine.dbtask import DBTask


class Convert(DBTask):
    def _convert(self, path, rootdir, tool, options, delete_original=True):
        tool.run(path, rootdir, options)

        relpath = PurePath(path).relative_to(rootdir).as_posix()
        EventIP.objects.create(
            eventType_id=50750,
            eventOutcome=EventIP.SUCCESS,
            eventOutcomeDetailNote='Converted {}'.format(relpath),
            linkingObjectIdentifierValue=str(self.get_information_package().pk),
        )

        if delete_original:
            os.remove(path)

    def run(self, tool, pattern, rootdir, options, delete_original=True):
        tool = ConversionTool.objects.get(name=tool)

        for path in iglob(rootdir + '/' + pattern, case_sensitive=False):
            if not in_directory(path, rootdir):
                raise ValueError('Invalid file-pattern accessing files outside of package')

            if os.path.isdir(path):
                for root, _dirs, files in os.walk(path):
                    for f in files:
                        fpath = os.path.join(root, f)
                        self._convert(fpath, rootdir, tool, options)
            else:
                self._convert(path, rootdir, tool, options)
