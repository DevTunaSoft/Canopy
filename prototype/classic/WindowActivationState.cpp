#include "WindowActivationState.h"

#include <QJsonValue>
#include <QMetaType>
#include <QtMath>

#include <algorithm>
#include <cmath>
#include <limits>

namespace {

QStringList approvedDockNames()
{
    return {QStringLiteral("Browser"), QStringLiteral("Mail"),
            QStringLiteral("Files"), QStringLiteral("Calendar"),
            QStringLiteral("Photos"), QStringLiteral("Music"),
            QStringLiteral("Terminal"), QStringLiteral("Settings")};
}

QStringList knownBackends()
{
    // Mirrors window_state_capabilities.KNOWN_BACKENDS ids only.
    return {QStringLiteral("x11"), QStringLiteral("wayland"),
            QStringLiteral("headless")};
}

QStringList focusStatuses()
{
    // Mirrors focus_intents decision statuses.
    return {QStringLiteral("GRANTED"), QStringLiteral("DENIED"),
            QStringLiteral("STALE_TARGET"), QStringLiteral("UNKNOWN_TARGET"),
            QStringLiteral("ACTIVATION_FAILED")};
}

QString grantKey(const QString &origin, const QString &target)
{
    return origin + QStringLiteral("\x1f") + target;
}

}  // namespace

WindowActivationState::WindowActivationState(QObject *parent) : QObject(parent)
{
}

QString WindowActivationState::status() const
{
    return m_trusted ? QStringLiteral("READY") : QStringLiteral("UNAVAILABLE");
}

QStringList WindowActivationState::runningApps() const
{
    if (!m_trusted) {
        return {};
    }
    QStringList names;
    for (const Owner &owner : m_owners) {
        if (!names.contains(owner.appId)) {
            names.append(owner.appId);
        }
    }
    std::sort(names.begin(), names.end());
    return names;
}

QStringList WindowActivationState::activeApps() const
{
    if (!m_trusted || !m_focusGranted || !isRunning(m_focusApp)) {
        return {};
    }
    return {m_focusApp};
}

bool WindowActivationState::isApprovedDockName(const QString &name)
{
    return approvedDockNames().contains(name);
}

bool WindowActivationState::isApprovedOrigin(const QString &name)
{
    return name == QStringLiteral("Canopy") || isApprovedDockName(name);
}

bool WindowActivationState::isKnownBackend(const QString &name)
{
    return knownBackends().contains(name);
}

bool WindowActivationState::asInt(const QVariant &value, int &out)
{
    if (!value.isValid()) {
        return false;
    }
    switch (value.typeId()) {
    case QMetaType::Int:
        out = value.toInt();
        return true;
    case QMetaType::UInt: {
        const quint64 v = value.toUInt();
        if (v > static_cast<quint64>(std::numeric_limits<int>::max())) {
            return false;
        }
        out = static_cast<int>(v);
        return true;
    }
    case QMetaType::LongLong: {
        const qlonglong v = value.toLongLong();
        if (v < std::numeric_limits<int>::min()
                || v > std::numeric_limits<int>::max()) {
            return false;
        }
        out = static_cast<int>(v);
        return true;
    }
    case QMetaType::Double: {
        // QJsonValue::toVariant() transports integers as doubles on some Qt
        // builds; accept only exactly integral, in-range values.
        const double v = value.toDouble();
        if (!std::isfinite(v) || qFloor(v) != v
                || v < static_cast<double>(std::numeric_limits<int>::min())
                || v > static_cast<double>(std::numeric_limits<int>::max())) {
            return false;
        }
        out = static_cast<int>(v);
        return true;
    }
    default:
        return false;  // bool, strings, containers and null never coerce
    }
}

bool WindowActivationState::asString(const QVariant &value, QString &out)
{
    if (!value.isValid() || value.typeId() != QMetaType::QString) {
        return false;
    }
    out = value.toString();
    return out.length() <= kMaxIdLength;
}

bool WindowActivationState::asBool(const QVariant &value, bool &out)
{
    if (!value.isValid() || value.typeId() != QMetaType::Bool) {
        return false;
    }
    out = value.toBool();
    return true;
}

bool WindowActivationState::parseOwners(const QVariantList &values,
                                        QList<Owner> &out) const
{
    if (values.size() > kMaxApps * kMaxPidsPerApp) {
        return false;
    }
    QSet<int> pids;
    QHash<QString, int> perApp;
    for (const QVariant &value : values) {
        if (value.typeId() != QMetaType::QVariantMap) {
            return false;
        }
        const QVariantMap item = value.toMap();
        if (!item.contains(QStringLiteral("pid"))
                || !item.contains(QStringLiteral("app_id"))) {
            return false;
        }
        int pid = 0;
        QString appId;
        if (!asInt(item.value(QStringLiteral("pid")), pid)
                || !asString(item.value(QStringLiteral("app_id")), appId)
                || pid < 1 || pid > kMaxPid
                || !isApprovedDockName(appId)
                || pids.contains(pid)) {
            return false;  // duplicate pid would invent two live processes
        }
        if (perApp.value(appId, 0) >= kMaxPidsPerApp) {
            return false;
        }
        pids.insert(pid);
        perApp.insert(appId, perApp.value(appId, 0) + 1);
        out.append(Owner{pid, appId});
    }
    if (perApp.size() > kMaxApps) {
        return false;
    }
    return true;
}

bool WindowActivationState::parseInstalled(const QVariantList &values,
                                           QSet<QString> &out) const
{
    if (values.size() > kMaxInstalled) {
        return false;
    }
    for (const QVariant &value : values) {
        QString name;
        if (!asString(value, name) || !isApprovedDockName(name)) {
            return false;
        }
        out.insert(name);
    }
    return true;
}

bool WindowActivationState::parseGrants(const QVariantList &values,
                                        QSet<QString> &out) const
{
    if (values.size() > kMaxGrants) {
        return false;
    }
    for (const QVariant &value : values) {
        if (value.typeId() != QMetaType::QVariantList) {
            return false;
        }
        const QVariantList pair = value.toList();
        if (pair.size() != 2) {
            return false;
        }
        QString origin;
        QString target;
        if (!asString(pair.at(0), origin) || !asString(pair.at(1), target)
                || !isApprovedOrigin(origin) || !isApprovedDockName(target)) {
            return false;
        }
        out.insert(grantKey(origin, target));
    }
    return true;
}

void WindowActivationState::clear()
{
    m_trusted = false;
    m_launcherEnabled = false;
    m_owners.clear();
    m_installed.clear();
    m_grants.clear();
    m_focusApp.clear();
    m_focusGranted = false;
    emit stateChanged();
}

bool WindowActivationState::applySnapshot(const QVariantMap &snapshot)
{
    static const QStringList required = {
        QStringLiteral("schema"), QStringLiteral("backend"),
        QStringLiteral("negotiation"), QStringLiteral("sequence"),
        QStringLiteral("installed"), QStringLiteral("owners"),
        QStringLiteral("grants"), QStringLiteral("launcherEnabled")};

    for (const QString &key : required) {
        if (!snapshot.contains(key)) {
            clear();
            return false;
        }
    }

    int schema = 0;
    int sequence = 0;
    QString backend;
    QString negotiation;
    bool launcherEnabled = false;
    if (!asInt(snapshot.value(QStringLiteral("schema")), schema)
            || schema != kSchema
            || !asInt(snapshot.value(QStringLiteral("sequence")), sequence)
            || sequence < 0
            || !asString(snapshot.value(QStringLiteral("backend")), backend)
            || !isKnownBackend(backend)
            || !asString(snapshot.value(QStringLiteral("negotiation")),
                         negotiation)
            || !QStringList({QStringLiteral("SUPPORTED"),
                             QStringLiteral("PARTIAL"),
                             QStringLiteral("UNSUPPORTED")})
                    .contains(negotiation)
            || !asBool(snapshot.value(QStringLiteral("launcherEnabled")),
                       launcherEnabled)) {
        clear();
        return false;
    }
    if (sequence <= m_sequence) {
        return false;  // stale: never rewind a derived indicator state
    }

    QVariantList installedValue;
    QVariantList ownersValue;
    QVariantList grantsValue;
    const QVariant installedVar = snapshot.value(QStringLiteral("installed"));
    const QVariant ownersVar = snapshot.value(QStringLiteral("owners"));
    const QVariant grantsVar = snapshot.value(QStringLiteral("grants"));
    if (installedVar.typeId() != QMetaType::QVariantList
            || ownersVar.typeId() != QMetaType::QVariantList
            || grantsVar.typeId() != QMetaType::QVariantList) {
        clear();
        return false;
    }
    installedValue = installedVar.toList();
    ownersValue = ownersVar.toList();
    grantsValue = grantsVar.toList();

    QSet<QString> installed;
    QList<Owner> owners;
    QSet<QString> grants;
    if (!parseInstalled(installedValue, installed)
            || !parseOwners(ownersValue, owners)
            || !parseGrants(grantsValue, grants)) {
        clear();
        return false;
    }

    QString focusApp;
    bool focusGranted = false;
    if (snapshot.contains(QStringLiteral("focus"))) {
        const QVariant focusVar = snapshot.value(QStringLiteral("focus"));
        if (focusVar.typeId() != QMetaType::QVariantMap) {
            clear();
            return false;
        }
        const QVariantMap focus = focusVar.toMap();
        static const QStringList focusKeys = {
            QStringLiteral("app_id"), QStringLiteral("window_id"),
            QStringLiteral("serial"), QStringLiteral("status")};
        int windowId = 0;
        int serial = 0;
        QString statusValue;
        for (const QString &key : focusKeys) {
            if (!focus.contains(key)) {
                clear();
                return false;
            }
        }
        if (!asString(focus.value(QStringLiteral("app_id")), focusApp)
                || !isApprovedDockName(focusApp)
                || !asInt(focus.value(QStringLiteral("window_id")), windowId)
                || windowId < 1 || windowId > kMaxPid
                || !asInt(focus.value(QStringLiteral("serial")), serial)
                || serial < 1
                || !asString(focus.value(QStringLiteral("status")), statusValue)
                || !focusStatuses().contains(statusValue)) {
            clear();
            return false;
        }
        focusGranted = statusValue == QStringLiteral("GRANTED");
    }

    m_sequence = sequence;
    m_trusted = true;
    m_launcherEnabled = launcherEnabled;
    m_installed = installed;
    m_owners = owners;
    m_grants = grants;
    m_focusApp = focusGranted ? focusApp : QString();
    m_focusGranted = focusGranted;
    emit stateChanged();
    return true;
}

bool WindowActivationState::isRunning(const QString &appId) const
{
    if (!m_trusted || !isApprovedDockName(appId)) {
        return false;
    }
    for (const Owner &owner : m_owners) {
        if (owner.appId == appId) {
            return true;
        }
    }
    return false;
}

int WindowActivationState::runningPidCount(const QString &appId) const
{
    if (!m_trusted || !isApprovedDockName(appId)) {
        return 0;
    }
    int count = 0;
    for (const Owner &owner : m_owners) {
        if (owner.appId == appId) {
            ++count;
        }
    }
    return count;
}

bool WindowActivationState::isActive(const QString &appId) const
{
    return m_trusted && m_focusGranted && isRunning(appId)
            && m_focusApp == appId;
}

bool WindowActivationState::authorized(const QString &origin,
                                       const QString &target) const
{
    if (origin == target) {
        return true;
    }
    return m_grants.contains(grantKey(origin, target));
}

QString WindowActivationState::resolveActivation(const QString &appId,
                                                 const QString &originApp) const
{
    if (!m_trusted || !isApprovedDockName(appId)
            || !isApprovedOrigin(originApp)) {
        return QStringLiteral("REJECT");
    }
    if (isRunning(appId)) {
        if (!m_launcherEnabled) {
            return QStringLiteral("IGNORE");
        }
        return authorized(originApp, appId) ? QStringLiteral("FOCUS")
                                            : QStringLiteral("REJECT");
    }
    if (m_installed.contains(appId) && m_launcherEnabled) {
        return QStringLiteral("LAUNCH");
    }
    return QStringLiteral("REJECT");
}
