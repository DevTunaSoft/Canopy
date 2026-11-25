// Minimal fake GIO declarations for the SystemAppLauncher fixture only.
// Implements exactly the symbols SystemAppLauncher.cpp calls; never installed
// into the repo and never linked alongside real GLib/GIO.
#pragma once

typedef int gboolean;
#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif

typedef struct _GAppInfo GAppInfo;

typedef struct _GError {
    int domain;
    int code;
    char *message;
} GError;

#ifdef __cplusplus
extern "C" {
#endif

gboolean g_app_info_should_show(GAppInfo *appinfo);
gboolean g_app_info_launch(GAppInfo *appinfo, void *files,
                           void *launch_context, GError **error);
void g_object_unref(void *object);
void g_error_free(GError *error);

#ifdef __cplusplus
}
#endif
