#ifndef CANOPY_REDUCED_MOTION_POLICY_H
#define CANOPY_REDUCED_MOTION_POLICY_H

// Pure, header-only policy for the Classic presentation's QML animations.
// It reads the native accessibility hint once per query and resolves it with
// the Canopy preference domain owned by
// canopy_features/accessibility/reduced_motion_contract.py. No visual input,
// timer, animation, file, socket or background service lives here.
#include <QString>
#include <QGuiApplication>
#if QT_VERSION >= QT_VERSION_CHECK(6, 12, 0)
#include <QAccessibilityHints>
#include <QStyleHints>
#endif

namespace canopyReducedMotion {

inline constexpr char UNSET[] = "unset";
inline constexpr char FULL[] = "full";
inline constexpr char REDUCE[] = "reduce";

// Unknown, malformed or foreign values are never treated as consent to motion.
inline QString normalize(const QString &value) {
    if (value == QLatin1String(REDUCE))
        return QStringLiteral("reduce");
    if (value == QLatin1String(FULL))
        return QStringLiteral("full");
    return QStringLiteral("unset");
}

// Qt 6.12 exposes the desktop's native motion preference through
// QStyleHints::accessibility(). NoPreference is *not* an opt-in to full
// motion; it stays unset so resolve() fails safe. Older supported Qt (6.4+)
// has no native hint and likewise reports unset rather than guessing.
inline QString nativePreference() {
#if QT_VERSION >= QT_VERSION_CHECK(6, 12, 0)
    const QAccessibilityHints *hints = QGuiApplication::styleHints()->accessibility();
    if (hints && hints->motionPreference() == Qt::MotionPreference::ReducedMotion)
        return QStringLiteral("reduce");
#endif
    return QStringLiteral("unset");
}

// System (native) < user, but a REDUCE from either source is authoritative.
// With no explicit preference the contract fails safe to REDUCE.
inline bool reduced(const QString &native, const QString &user) {
    const QString n = normalize(native);
    const QString u = normalize(user);
    if (n == QLatin1String(REDUCE) || u == QLatin1String(REDUCE))
        return true;
    if (n == QLatin1String(FULL) || u == QLatin1String(FULL))
        return false;
    return true; // fail safe to reduce: default is "no preference" -> REDUCE
}

// The one duration function QML animations bind to. Reduced motion means an
// instant state change: no tweening, no extra frames and no visual redesign.
inline int duration(int nominalMs, bool isReduced) {
    if (nominalMs <= 0)
        return 0;
    return isReduced ? 0 : nominalMs;
}

} // namespace canopyReducedMotion

#endif // CANOPY_REDUCED_MOTION_POLICY_H
