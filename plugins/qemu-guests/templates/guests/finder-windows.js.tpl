ObjC.import('AppKit');
ObjC.import('CoreGraphics');

const apps = $.NSRunningApplication.runningApplicationsWithBundleIdentifier('com.apple.finder');
if (Number(apps.count) !== 1) throw Error('Finder process is missing or ambiguous');
const pid = Number(apps.objectAtIndex(0).processIdentifier);
const raw = $.CGWindowListCopyWindowInfo(1, 0);
const windows = ObjC.deepUnwrap(ObjC.castRefToObject(raw));
JSON.stringify(windows.filter(window => window.kCGWindowOwnerPID === pid && window.kCGWindowLayer === 0)
    .map(window => ({number: window.kCGWindowNumber, x: window.kCGWindowBounds.X,
        y: window.kCGWindowBounds.Y, width: window.kCGWindowBounds.Width,
        height: window.kCGWindowBounds.Height})));
