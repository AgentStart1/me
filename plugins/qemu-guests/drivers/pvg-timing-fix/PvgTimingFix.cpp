#include <Headers/kern_api.hpp>
#include <Headers/plugin_start.hpp>
#include <IOKit/graphics/IOGraphicsTypes.h>
#include "StockTimingMethod.hpp"

namespace {
using DetailedTiming = const IODetailedTimingInformationV2 *(*)(void *, int);
DetailedTiming detailedTiming;
mach_vm_address_t originalTiming;
uint32_t timingCalls;

const char *driverPaths[] {
    "/System/Library/Extensions/AppleParavirtGPU.kext/Contents/MacOS/AppleParavirtGPU",
};
KernelPatcher::KextInfo driver {
    "com.apple.driver.AppleParavirtGPU", driverPaths, arrsize(driverPaths), {true}, {},
    KernelPatcher::KextInfo::Unloaded,
};

IOReturn timingInfo(void *framebuffer, int mode, IOTimingInformation *information) {
    auto result = FunctionCast(timingInfo, originalTiming)(framebuffer, mode, information);
    if (result != kIOReturnSuccess || !information) return result;

    // This layout is guarded by the exact stock method bytes before routing.
    auto timings = *reinterpret_cast<void **>(static_cast<uint8_t *>(framebuffer) + 0x1f8);
    auto timing = detailedTiming(timings, mode);
    if (!timing || !timing->pixelClock || !timing->horizontalActive || !timing->verticalActive ||
        timing->minPixelClock != timing->pixelClock || timing->maxPixelClock != timing->pixelClock) {
        return result;
    }

    // The stock driver clears this flag even though it owns a complete V2 timing.
    // Publishing it lets IOFramebuffer retain the nominal VBL interval instead
    // of replacing vblDeltaReal with each timer callback's scheduling jitter.
    information->detailedInfo.v2 = *timing;
    information->flags |= kIODetailedTimingValid;
    auto calls = __atomic_add_fetch(&timingCalls, 1, __ATOMIC_RELAXED);
    if (auto service = ADDPR(selfInstance)) {
        service->setProperty("DetailedTimingCalls", calls, 32);
        service->setProperty("NominalPixelClock", timing->pixelClock, 64);
    }
    return result;
}

void loaded(void *, KernelPatcher &patcher, size_t index, mach_vm_address_t address, size_t size) {
    if (index != driver.loadIndex) return;
    auto method = patcher.solveSymbol(index,
        "__ZN24AppleParavirtFramebuffer27getTimingInfoForDisplayModeEiP19IOTimingInformation", address, size);
    auto helper = patcher.solveSymbol(index, "__ZL17getDetailedTimingP7OSArrayi", address, size);
    if (!method || !helper || memcmp(reinterpret_cast<const void *>(method), stockTimingMethod,
                                      sizeof(stockTimingMethod)) != 0) {
        SYSLOG("timing", "stock driver does not match the audited macOS 15.8.1 implementation; inactive");
        patcher.clearError();
        return;
    }
    detailedTiming = reinterpret_cast<DetailedTiming>(helper);
    KernelPatcher::RouteRequest request {
        "__ZN24AppleParavirtFramebuffer27getTimingInfoForDisplayModeEiP19IOTimingInformation",
        timingInfo, originalTiming,
    };
    bool routed = patcher.routeMultiple(index, &request, 1, address, size);
    if (auto service = ADDPR(selfInstance)) service->setProperty("TimingRouteInstalled", routed);
    SYSLOG("timing", "detailed timing route installed: %d", routed);
    patcher.clearError();
}

void start() { lilu.onKextLoadForce(&driver, 1, loaded); }
const char *offArguments[] {"-pvgtimingoff"};
const char *debugArguments[] {"-pvgtimingdbg"};
} // namespace

PluginConfiguration ADDPR(config) {
    xStringify(PRODUCT_NAME), parseModuleVersion(xStringify(MODULE_VERSION)), LiluAPI::AllowNormal,
    offArguments, arrsize(offArguments), debugArguments, arrsize(debugArguments), nullptr, 0,
    KernelVersion::Sequoia, KernelVersion::Sequoia, start,
};

extern "C" kern_return_t ADDPR(kern_start)(kmod_info_t *, void *);
extern "C" kern_return_t ADDPR(kern_stop)(kmod_info_t *, void *);
KMOD_EXPLICIT_DECL(com.example.PvgTimingFix, xStringify(MODULE_VERSION), ADDPR(kern_start), ADDPR(kern_stop))
