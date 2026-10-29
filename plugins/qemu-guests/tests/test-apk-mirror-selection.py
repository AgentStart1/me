"""Offline mirror selection using the real guest Shell selector."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'tests'))
from shell_test_support import ShellTestCase


class MirrorTests(ShellTestCase):
    def setUp(self):
        super().setUp()
        self.mock('setup-apkrepos', '''printf '%s\n' "$*" > "$MOCK_SETUP_LOG"
case "$MOCK_SETUP_RESULT" in ok) ;; empty) exit 0;; *) exit 1;; esac
printf '%s\n' 'http://fast.example/alpine/v3.24/main' 'http://fast.example/alpine/v3.24/community' > "$APK_REPOSITORIES_FILE"''')
        self.mock('apk', '''repository="$(head -n 1 "$APK_REPOSITORIES_FILE")"
echo "$repository" >> "$MOCK_APK_LOG"
[[ "$repository" == "$ACCEPTED_MIRROR/"* ]]''')

    def select(self, base, accepted, detection='ok'):
        self.write('answers', 'APKREPOSOPTS="placeholder"\n')
        return self.run_shell('bash "$REPOSITORY/plugins/qemu-guests/scripts/select-apk-mirror.sh" v3.24 "$1" "$FIXTURE/answers"', base,
                              env=dict(APK_REPOSITORIES_FILE=self.path(self.root / 'repositories'),
                                       ALPINE_SELECTED_MIRROR_FILE=self.path(self.root / 'selected'),
                                       MOCK_SETUP_LOG=self.path(self.root / 'setup.log'),
                                       MOCK_APK_LOG=self.path(self.root / 'apk.log'),
                                       MOCK_SETUP_RESULT=detection, ACCEPTED_MIRROR=accepted), status=None)

    def test_automatic_selection_and_fallback(self):
        for detection, accepted in [('ok', 'https://fast.example/alpine'),
                                    ('ok', 'https://dl-cdn.alpinelinux.org/alpine'),
                                    ('fail', 'https://dl-cdn.alpinelinux.org/alpine'),
                                    ('empty', 'https://dl-cdn.alpinelinux.org/alpine')]:
            with self.subTest(detection=detection, accepted=accepted):
                for name in ('repositories', 'selected', 'setup.log', 'apk.log'):
                    (self.root / name).unlink(missing_ok=True)
                result = self.select('auto', accepted, detection)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), accepted)
                self.assertIn(accepted + '/v3.24/main', self.read('answers'))
                self.assertEqual(self.read('setup.log').strip(), '-cf')
                self.assertIn(accepted + '/v3.24/main', self.read('apk.log'))
                if detection == 'ok':
                    self.assertIn('https://fast.example/alpine/v3.24/main', self.read('apk.log'))

    def test_manual_mirror_skips_detection_and_persists(self):
        result = self.select('https://mirror.example/alpine/', 'https://mirror.example/alpine')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'https://mirror.example/alpine')
        self.assert_missing('setup.log')
        self.assertIn('https://mirror.example/alpine/v3.24/community', self.read('answers'))

    def test_invalid_or_unavailable_manual_mirror_is_rejected(self):
        for base in ('https://mirror.example/alpine', 'file:///tmp/alpine'):
            with self.subTest(base=base):
                self.assertNotEqual(self.select(base, 'https://unavailable.example').returncode, 0)


if __name__ == '__main__':
    unittest.main()
