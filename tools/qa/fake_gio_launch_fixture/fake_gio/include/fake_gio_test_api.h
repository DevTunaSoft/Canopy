// Fixture-only controls; not part of the fake GIO surface seen by production.
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/* available_csv / launch_fail_csv are comma-separated desktop IDs. */
void fake_gio_configure(const char *available_csv,
                        const char *launch_fail_csv,
                        const char *log_path);
void fake_gio_reset_log(void);

#ifdef __cplusplus
}
#endif
