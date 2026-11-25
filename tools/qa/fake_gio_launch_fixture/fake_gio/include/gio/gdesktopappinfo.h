// Fake gdesktopappinfo header: one desktop-ID constructor plus the G_APP_INFO
// cast macro used by the unmodified production source.
#pragma once
#include <gio/gio.h>

typedef GAppInfo GDesktopAppInfo;

#define G_APP_INFO(appinfo) ((GAppInfo *)(appinfo))

#ifdef __cplusplus
extern "C" {
#endif

GDesktopAppInfo *g_desktop_app_info_new(const char *desktop_id);

#ifdef __cplusplus
}
#endif
