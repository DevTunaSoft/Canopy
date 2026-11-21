#pragma once

#include <QObject>
#include <QString>
#include <QStringList>

// Host-owned, opt-in launching of named Linux desktop applications.
// Uses the system's GIO desktop database (no shell, no user-provided Exec).
// Prototype only: this is NOT a Canopy session, app index or sandbox.
class SystemAppLauncher final : public QObject {
    Q_OBJECT
public:
    explicit SystemAppLauncher(bool enabled, QObject *parent = nullptr);

    Q_INVOKABLE bool canLaunch(const QString &dockName) const;
    Q_INVOKABLE bool launch(const QString &dockName) const;
    bool isEnabled() const { return m_enabled; }

private:
    static QStringList candidatesFor(const QString &dockName);
    bool m_enabled;
};
