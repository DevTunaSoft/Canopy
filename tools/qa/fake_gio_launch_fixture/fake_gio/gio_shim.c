/* Deterministic fake GIO library for the SystemAppLauncher fixture.
 * Every call is appended to a log as "<event> <desktop-id>" so the harness can
 * prove exactly which desktop ID each dock label reached. No desktop database,
 * no process launch, no shell, no user application is involved.
 */
#include <gio/gdesktopappinfo.h>
#include <fake_gio_test_api.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct _GAppInfo {
    char id[256];
};

static char available_csv[4096];
static char failing_csv[4096];
static char log_path[1024];

void fake_gio_reset_log(void);

void fake_gio_configure(const char *available, const char *failing,
                        const char *path) {
    snprintf(available_csv, sizeof available_csv, "%s", available ? available : "");
    snprintf(failing_csv, sizeof failing_csv, "%s", failing ? failing : "");
    snprintf(log_path, sizeof log_path, "%s", path ? path : "");
    fake_gio_reset_log();
}

void fake_gio_reset_log(void) {
    if (!log_path[0])
        return;
    FILE *file = fopen(log_path, "w");
    if (file)
        fclose(file);
}

static void record(const char *event, const char *id) {
    if (!log_path[0])
        return;
    FILE *file = fopen(log_path, "a");
    if (!file)
        return;
    fprintf(file, "%s %s\n", event, id ? id : "");
    fclose(file);
}

/* Exact comma-separated token match; no substring or prefix matches. */
static int csv_contains(const char *csv, const char *needle) {
    if (!csv || !needle || !*needle)
        return 0;
    size_t wanted = strlen(needle);
    const char *cursor = csv;
    while (*cursor) {
        while (*cursor == ',' || *cursor == ' ' || *cursor == '\t')
            ++cursor;
        const char *start = cursor;
        while (*cursor && *cursor != ',')
            ++cursor;
        size_t length = (size_t)(cursor - start);
        while (length > 0 && (start[length - 1] == ' ' || start[length - 1] == '\t'))
            --length;
        if (length == wanted && memcmp(start, needle, wanted) == 0)
            return 1;
    }
    return 0;
}

GDesktopAppInfo *g_desktop_app_info_new(const char *desktop_id) {
    record("new", desktop_id);
    if (!desktop_id || !csv_contains(available_csv, desktop_id))
        return NULL;
    GAppInfo *info = (GAppInfo *)calloc(1, sizeof *info);
    if (!info)
        return NULL;
    snprintf(info->id, sizeof info->id, "%s", desktop_id);
    return (GDesktopAppInfo *)info;
}

gboolean g_app_info_should_show(GAppInfo *appinfo) {
    record("should_show", appinfo ? appinfo->id : "");
    return TRUE;
}

gboolean g_app_info_launch(GAppInfo *appinfo, void *files,
                           void *launch_context, GError **error) {
    (void)files;
    (void)launch_context;
    const char *id = appinfo ? appinfo->id : "";
    record("launch", id);
    if (csv_contains(failing_csv, id)) {
        if (error)
            *error = (GError *)calloc(1, sizeof(GError));
        return FALSE;
    }
    return TRUE;
}

void g_object_unref(void *object) {
    free(object);
}

void g_error_free(GError *error) {
    free(error);
}
