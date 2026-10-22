using System;
using System.Runtime.InteropServices;

namespace GuestDesktop {
    public class ScreenInfo {
        public int Width { get; set; }
        public int Height { get; set; }
        public uint Dpi { get; set; }
    }
    public static class Display {
        [DllImport("user32.dll", CharSet=CharSet.Unicode)]
        static extern bool EnumDisplaySettings(string device, uint mode, IntPtr data);
        [DllImport("user32.dll", CharSet=CharSet.Unicode)]
        static extern int ChangeDisplaySettings(IntPtr data, uint flags);
        [DllImport("user32.dll")]
        static extern bool SetProcessDpiAwarenessContext(IntPtr context);
        [DllImport("user32.dll")]
        static extern uint GetDpiForSystem();

        public static ScreenInfo Configure(int width, int height) {
            SetProcessDpiAwarenessContext(new IntPtr(-4));
            IntPtr mode = Marshal.AllocHGlobal(220);
            try {
                bool found = false;
                for (uint i = 0; i < 4096; i++) {
                    Marshal.Copy(new byte[220], 0, mode, 220);
                    Marshal.WriteInt16(mode, 68, 220);
                    if (!EnumDisplaySettings(null, i, mode)) break;
                    if (Marshal.ReadInt32(mode, 172) == width && Marshal.ReadInt32(mode, 176) == height &&
                        Marshal.ReadInt32(mode, 168) == 32) {
                        int result = ChangeDisplaySettings(mode, 1);
                        if (result != 0) throw new InvalidOperationException("Display change failed: " + result);
                        found = true;
                        break;
                    }
                }
                if (!found) throw new InvalidOperationException("Requested desktop mode is unavailable");
                Marshal.WriteInt16(mode, 68, 220);
                if (!EnumDisplaySettings(null, UInt32.MaxValue, mode)) throw new InvalidOperationException("Display probe failed");
                ScreenInfo screen = new ScreenInfo { Width = Marshal.ReadInt32(mode, 172), Height = Marshal.ReadInt32(mode, 176), Dpi = GetDpiForSystem() };
                if (screen.Width != width || screen.Height != height || screen.Dpi != 96)
                    throw new InvalidOperationException("Desktop geometry/DPI did not match the configured test environment");
                return screen;
            } finally { Marshal.FreeHGlobal(mode); }
        }
    }
}
