"""Offline SDK installation through the public Shell entry."""
from pathlib import Path
import sys
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
from shell_test_support import ShellTestCase


class InstallSdkTests(ShellTestCase):
    def setUp(self):
        super().setUp()
        self.mock('curl', '''while [ $# -gt 0 ]; do
    if [ "$1" = -o ]; then cp "$FAKE_ARCHIVE" "$2"; echo download >> "$FAKE_LOG"; exit; fi
    shift
done
exit 1''')
        self.mock('sdkmanager', 'echo "sdkmanager $*" >> "$FAKE_LOG"')
        self.mock('sudo', 'echo forbidden-sudo >> "$FAKE_LOG"; exit 99')
        archive_path = self.root / 'tools.zip'
        with zipfile.ZipFile(archive_path, 'w') as archive:
            entry = zipfile.ZipInfo('cmdline-tools/bin/sdkmanager')
            entry.external_attr = 0o100755 << 16
            archive.writestr(entry, '#!/bin/sh\nexit 0\n')
            archive.writestr('cmdline-tools/source.properties', 'Pkg.Revision=20.0\n')
        self.env.update(FAKE_ARCHIVE=self.path(archive_path), FAKE_LOG=self.path(self.root / 'calls'),
                        ANDROID_HOME=self.path(self.root / 'sdk'))
        self.write('project/commandline-tools.zip', 'project-owned')

    def install(self):
        return self.run_shell('cd "$FIXTURE/project"\nbash "$REPOSITORY/plugins/android-emulator-profile/scripts/install-sdk.sh"')

    def test_download_preserves_project_archive_and_never_uses_sudo(self):
        self.install()
        self.assertTrue((self.root / 'sdk/cmdline-tools/latest/bin/sdkmanager').is_file())
        self.assertEqual(self.read('project/commandline-tools.zip'), 'project-owned')
        self.assertNotIn('forbidden-sudo', self.read('calls'))

    def test_newer_tools_are_reused_without_download(self):
        self.write('sdk/cmdline-tools/latest/source.properties', 'Pkg.Revision=20.0.1\n')
        self.write('sdk/cmdline-tools/latest/bin/sdkmanager', '#!/bin/sh\nexit 0\n', True)
        self.install()
        self.assertNotIn('download', self.read('calls'))
        self.assertEqual(self.read('sdk/cmdline-tools/latest/source.properties'), 'Pkg.Revision=20.0.1\n')

    def test_upgrade_preserves_previous_tools(self):
        self.write('sdk/cmdline-tools/latest/source.properties', 'Pkg.Revision=19.0\n')
        self.write('sdk/cmdline-tools/latest/bin/sdkmanager', '#!/bin/sh\nexit 0\n', True)
        self.write('sdk/cmdline-tools/latest/preserved-file', 'previous')
        self.install()
        backups = list((self.root / 'sdk/cmdline-tools').glob('previous.*/latest/preserved-file'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), 'previous')
        self.assertEqual(self.read('project/commandline-tools.zip'), 'project-owned')


if __name__ == '__main__':
    unittest.main()
