#include "RoundedDockIconProvider.h"
#include "SystemAppLauncher.h"
#include "WindowActivationState.h"

#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQuickWindow>
#include <QQuickItem>
#include <QtMath>
#include <QDebug>
#include <QTimer>
#include <QDateTime>
#include <QCursor>
#include <QCoreApplication>
#include <QImage>
#include <QImageReader>
#include <QStringList>
#include <QRegularExpression>
#include <QSet>
#include <QVector>
#include <QQmlContext>
#include <QQmlComponent>
#include <QShortcut>
#include <QKeySequence>
#include <QCryptographicHash>
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QJsonParseError>
#include <QQmlComponent>
#include <QQmlProperty>
#include <QUrl>

static void showActivationStatus(QObject *status, const QString &message);
static QString activationRefusal(const WindowActivationState &state,
                                 const QString &name,
                                 const QString &intent);

// Host-side adapter for the single frozen Files dock interaction. It owns
// no launcher logic: it forwards only the exact dock label to the existing
// SystemAppLauncher and reports a refusal in the existing launcher footer.
class FilesDockLaunchBridge final : public QObject {
    Q_OBJECT
public:
    FilesDockLaunchBridge(SystemAppLauncher &launcher, WindowActivationState &state,
                          QObject *statusOverlay, QObject *parent = nullptr)
        : QObject(parent), m_launcher(launcher), m_state(state), m_status(statusOverlay) {}

public slots:
    void activate(const QString &name) {
        if (name != QStringLiteral("Files")) {
            qWarning() << "CANOPY_FILES_DOCK_REJECTED: unknown action";
            return;
        }
        const QString intent = m_state.resolveActivation(
            name, QStringLiteral("Canopy"));
        if (intent != QStringLiteral("LAUNCH")) {
            qWarning() << "CANOPY_FILES_DOCK_INTENT_REFUSED" << intent;
            showActivationStatus(m_status, activationRefusal(m_state, name, intent));
            return;
        }
        // Intent is authoritative: only LAUNCH may reach the GIO service.
        if (m_launcher.launch(name)) {
            qInfo() << "CANOPY_FILES_DOCK_LAUNCH_REQUESTED";
            return;
        }
        qWarning() << "CANOPY_FILES_DOCK_LAUNCH_REFUSED";
        if (!m_status)
            return;
        // openLauncher() clears the prior message, so set the refusal
        // AFTER opening; the existing footer Label binds to this text.
        if (!QMetaObject::invokeMethod(m_status, "openLauncher",
                                       Qt::DirectConnection)) {
            qWarning() << "CANOPY_FILES_DOCK_STATUS_UNAVAILABLE";
            return;
        }
        m_status->setProperty("selectionMessage",
                              QStringLiteral("Files could not be launched"));
    }

private:
    SystemAppLauncher &m_launcher;
    WindowActivationState &m_state;
    QObject *m_status;
};

// Workstream A: the Browser dock tile uses the SAME validated SystemAppLauncher
// service through an adapter identical in shape to the Files one above. It owns
// no launcher logic, accepts only the exact frozen dock label, and reports a
// refusal in the existing launcher footer. No QML, artwork, geometry or colour
// changes; this bridge mirrors the reviewed Files adapter rather than adding
// any second GIO/shell code path.
class BrowserDockLaunchBridge final : public QObject {
    Q_OBJECT
public:
    BrowserDockLaunchBridge(SystemAppLauncher &launcher, WindowActivationState &state,
                            QObject *statusOverlay, QObject *parent = nullptr)
        : QObject(parent), m_launcher(launcher), m_state(state), m_status(statusOverlay) {}

public slots:
    void activate(const QString &name) {
        if (name != QStringLiteral("Browser")) {
            qWarning() << "CANOPY_BROWSER_DOCK_REJECTED: unknown action";
            return;
        }
        const QString intent = m_state.resolveActivation(
            name, QStringLiteral("Canopy"));
        if (intent != QStringLiteral("LAUNCH")) {
            qWarning() << "CANOPY_BROWSER_DOCK_INTENT_REFUSED" << intent;
            showActivationStatus(m_status, activationRefusal(m_state, name, intent));
            return;
        }
        // Intent is authoritative: only LAUNCH may reach the GIO service.
        if (m_launcher.launch(name)) {
            qInfo() << "CANOPY_BROWSER_DOCK_LAUNCH_REQUESTED";
            return;
        }
        qWarning() << "CANOPY_BROWSER_DOCK_LAUNCH_REFUSED";
        if (!m_status)
            return;
        // openLauncher() clears the prior message, so set the refusal
        // AFTER opening; the existing footer Label binds to this text.
        if (!QMetaObject::invokeMethod(m_status, "openLauncher",
                                       Qt::DirectConnection)) {
            qWarning() << "CANOPY_BROWSER_DOCK_STATUS_UNAVAILABLE";
            return;
        }
        m_status->setProperty("selectionMessage",
                              QStringLiteral("Browser could not be launched"));
    }

private:
    SystemAppLauncher &m_launcher;
    WindowActivationState &m_state;
    QObject *m_status;
};

// Workstream A third app: the Mail dock tile uses the SAME validated
// SystemAppLauncher service through an adapter identical in shape to the
// reviewed Files/Browser ones. It owns no launcher logic, accepts only the
// exact frozen dock label, and reports a refusal in the existing launcher
// footer. No QML, artwork, geometry or colour changes; no second GIO/shell
// code path is introduced.
class MailDockLaunchBridge final : public QObject {
    Q_OBJECT
public:
    MailDockLaunchBridge(SystemAppLauncher &launcher, WindowActivationState &state,
                         QObject *statusOverlay, QObject *parent = nullptr)
        : QObject(parent), m_launcher(launcher), m_state(state), m_status(statusOverlay) {}

public slots:
    void activate(const QString &name) {
        if (name != QStringLiteral("Mail")) {
            qWarning() << "CANOPY_MAIL_DOCK_REJECTED: unknown action";
            return;
        }
        const QString intent = m_state.resolveActivation(
            name, QStringLiteral("Canopy"));
        if (intent != QStringLiteral("LAUNCH")) {
            qWarning() << "CANOPY_MAIL_DOCK_INTENT_REFUSED" << intent;
            showActivationStatus(m_status, activationRefusal(m_state, name, intent));
            return;
        }
        // Intent is authoritative: only LAUNCH may reach the GIO service.
        if (m_launcher.launch(name)) {
            qInfo() << "CANOPY_MAIL_DOCK_LAUNCH_REQUESTED";
            return;
        }
        qWarning() << "CANOPY_MAIL_DOCK_LAUNCH_REFUSED";
        if (!m_status)
            return;
        // openLauncher() clears the prior message, so set the refusal
        // AFTER opening; the existing footer Label binds to this text.
        if (!QMetaObject::invokeMethod(m_status, "openLauncher",
                                       Qt::DirectConnection)) {
            qWarning() << "CANOPY_MAIL_DOCK_STATUS_UNAVAILABLE";
            return;
        }
        m_status->setProperty("selectionMessage",
                              QStringLiteral("Mail could not be launched"));
    }

private:
    SystemAppLauncher &m_launcher;
    WindowActivationState &m_state;
    QObject *m_status;
};

// Host-owned window-activation snapshot source. The adapter itself never
// observes or actuates; the shell supplies only facts it already owns:
// the Qt platform backend and the GIO launcher allowlist. No process or
// window telemetry is invented: owners/grants/focus stay empty unless a
// trusted host snapshot is explicitly supplied.
static QString activationBackendId()
{
    const QString platform = QGuiApplication::platformName().toLower();
    if (platform.contains(QStringLiteral("wayland")))
        return QStringLiteral("wayland");
    if (platform.contains(QStringLiteral("xcb"))
            || platform.contains(QStringLiteral("x11")))
        return QStringLiteral("x11");
    if (platform.contains(QStringLiteral("offscreen"))
            || platform.contains(QStringLiteral("minimal")))
        return QStringLiteral("headless");
    return QString();  // unknown backend: adapter fails closed
}

static QVariantMap hostActivationSnapshot(SystemAppLauncher &launcher,
                                          const QString &backend,
                                          int sequence)
{
    QVariantMap snapshot;
    snapshot.insert(QStringLiteral("schema"), WindowActivationState::kSchema);
    snapshot.insert(QStringLiteral("sequence"), sequence);
    snapshot.insert(QStringLiteral("backend"), backend);
    snapshot.insert(QStringLiteral("negotiation"),
                    backend.isEmpty()
                        ? QStringLiteral("UNSUPPORTED")
                        : (backend == QStringLiteral("headless")
                               ? QStringLiteral("PARTIAL")
                               : QStringLiteral("SUPPORTED")));
    snapshot.insert(QStringLiteral("launcherEnabled"), launcher.isEnabled());

    QVariantList installed;
    static const QStringList approved = {
        QStringLiteral("Browser"), QStringLiteral("Mail"),
        QStringLiteral("Files"), QStringLiteral("Calendar"),
        QStringLiteral("Photos"), QStringLiteral("Music"),
        QStringLiteral("Terminal"), QStringLiteral("Settings")
    };
    for (const QString &name : approved) {
        if (launcher.canLaunch(name))
            installed.append(name);
    }
    snapshot.insert(QStringLiteral("installed"), installed);
    snapshot.insert(QStringLiteral("owners"), QVariantList());
    snapshot.insert(QStringLiteral("grants"), QVariantList());
    return snapshot;
}

static bool applyActivationJson(WindowActivationState &state,
                                const QByteArray &json)
{
    QJsonParseError parseError{};
    const QJsonDocument document = QJsonDocument::fromJson(json, &parseError);
    if (parseError.error != QJsonParseError::NoError || !document.isObject()) {
        state.applySnapshot(QVariantMap());  // clear every indicator
        return false;
    }
    return state.applySnapshot(document.toVariant().toMap());
}

static bool loadActivationSnapshotFile(WindowActivationState &state,
                                       const QString &path)
{
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly) || file.size() > 65536) {
        state.applySnapshot(QVariantMap());
        return false;
    }
    return applyActivationJson(state, file.readAll());
}

static void showActivationStatus(QObject *status, const QString &message)
{
    if (!status)
        return;
    // openLauncher() clears the prior message, so set the disclosure AFTER
    // opening; the existing footer Label binds to this text.
    if (!QMetaObject::invokeMethod(status, "openLauncher", Qt::DirectConnection))
        return;
    status->setProperty("selectionMessage", message);
}

static QString activationRefusal(const WindowActivationState &state,
                                 const QString &name,
                                 const QString &intent)
{
    if (state.status() != QStringLiteral("READY"))
        return name + QStringLiteral(" window activation state unavailable");
    if (intent == QStringLiteral("FOCUS"))
        return name + QStringLiteral(" is running; focus is unavailable");
    if (intent == QStringLiteral("IGNORE"))
        return name + QStringLiteral(" activation ignored: launcher disabled");
    return name + QStringLiteral(" could not be launched");
}

// The remaining approved dock tiles use the same fail-closed intent gate.
// FOCUS is disclosed rather than actuated: Classic owns no window-focus
// backend, so claiming focus would be a false success.
class IntentDockBridge final : public QObject {
    Q_OBJECT
public:
    IntentDockBridge(SystemAppLauncher &launcher, WindowActivationState &state,
                     QObject *statusOverlay, QObject *parent = nullptr)
        : QObject(parent), m_launcher(launcher), m_state(state),
          m_status(statusOverlay) {}

public slots:
    void activate(const QString &name) {
        const QString intent = m_state.resolveActivation(
            name, QStringLiteral("Canopy"));
        if (intent == QStringLiteral("LAUNCH")) {
            if (m_launcher.launch(name))
                qInfo() << "CANOPY_INTENT_DOCK_LAUNCH_REQUESTED" << name;
            else
                showActivationStatus(m_status, activationRefusal(
                                         m_state, name, QStringLiteral("REJECT")));
            return;
        }
        qWarning() << "CANOPY_INTENT_DOCK_REFUSED" << name << intent;
        showActivationStatus(m_status, activationRefusal(m_state, name, intent));
    }

private:
    SystemAppLauncher &m_launcher;
    WindowActivationState &m_state;
    QObject *m_status;
};

// A Repeater can give its delegates QObject owners different from their
// visual parents. Traverse the actual QQuickItem scene tree for UI assertions.
static QQuickItem *findVisualItem(QQuickItem *parent, const QString &name) {
    if (!parent)
        return nullptr;
    if (parent->objectName() == name)
        return parent;
    for (QQuickItem *child : parent->childItems()) {
        if (auto *match = findVisualItem(child, name))
            return match;
    }
    return nullptr;
}

// Find the named dock control in the *visual* tree, including Repeater items.
static QQuickItem *findDockTile(QQuickItem *parent, const QString &iconName) {
    if (!parent)
        return nullptr;
    if (parent->objectName() == QStringLiteral("canopyDockTile") &&
        parent->property("iconName").toString() == iconName)
        return parent;
    for (QQuickItem *child : parent->childItems()) {
        if (auto *match = findDockTile(child, iconName))
            return match;
    }
    return nullptr;
}

static int countReadyFolderTiles(QQuickItem *parent) {
    if (!parent)
        return 0;
    int ready = parent->objectName() == QStringLiteral("canopyFolderTile")
                && parent->property("imageReady").toBool() ? 1 : 0;
    for (QQuickItem *child : parent->childItems())
        ready += countReadyFolderTiles(child);
    return ready;
}

static int countReadyDockTiles(QQuickItem *parent) {
    if (!parent)
        return 0;
    int ready = parent->objectName() == QStringLiteral("canopyDockTile")
                && parent->property("iconReady").toBool() ? 1 : 0;
    for (QQuickItem *child : parent->childItems())
        ready += countReadyDockTiles(child);
    return ready;
}

static QVariant tileProperty(const QObject *object, const QString &name)
{
    return object->property(name.toUtf8().constData());
}

static void setTileProperty(QObject *object, const QString &name,
                            const QVariant &value)
{
    object->setProperty(name.toUtf8().constData(), value);
}

// Apply trusted state to the frozen DockTile QObjects from the host. No
// visual QML byte is changed: these are dynamic object properties and the
// existing accessibility attached property, updated only on stateChanged.
static void updateDockActivationProperties(QQuickItem *root,
                                           WindowActivationState &state,
                                           QObject *adapter)
{
    if (!root || !adapter)
        return;
    const bool available = adapter->property("indicatorsAvailable").toBool();
    const int sequence = adapter->property("sequence").toInt();
    static const QStringList approved = {
        QStringLiteral("Browser"), QStringLiteral("Mail"),
        QStringLiteral("Files"), QStringLiteral("Calendar"),
        QStringLiteral("Photos"), QStringLiteral("Music"),
        QStringLiteral("Terminal"), QStringLiteral("Settings")
    };
    for (const QString &name : approved) {
        QQuickItem *tile = findDockTile(root, name);
        if (!tile)
            continue;
        const bool running = available && state.isRunning(name);
        const bool active = available && state.isActive(name);
        const QString intent = available
                ? state.resolveActivation(name, QStringLiteral("Canopy"))
                : QStringLiteral("REJECT");
        setTileProperty(tile, QStringLiteral("activationAvailable"), available);
        setTileProperty(tile, QStringLiteral("activationSequence"), sequence);
        setTileProperty(tile, QStringLiteral("windowRunning"), running);
        setTileProperty(tile, QStringLiteral("windowActive"), active);
        setTileProperty(tile, QStringLiteral("activationIntent"), intent);

        QString description;
        if (!available)
            description = name + QStringLiteral(" window activation state unavailable");
        else if (active)
            description = name + QStringLiteral(" active window");
        else if (running)
            description = name + QStringLiteral(" running; focus requires an explicit grant");
        else if (intent == QStringLiteral("LAUNCH"))
            description = name + QStringLiteral(" available to launch");
        else if (intent == QStringLiteral("IGNORE"))
            description = name + QStringLiteral(" activation ignored");
        else
            description = name + QStringLiteral(" preview only; not installed in this session");
        QQmlProperty accessibleDescription(
            tile, QStringLiteral("Accessible.description"),
            QQmlEngine::contextForObject(tile));
        if (accessibleDescription.isValid())
            accessibleDescription.write(description);
    }
}

// A rendered launcher must contain actual ready QML Image objects.
// A centered GridView rectangle or successful icon catalog lookup alone
// does not prove that the approved resource decoded.
static int countReadyLauncherImages(QQuickItem *parent) {
    if (!parent)
        return 0;
    int ready = parent->objectName() == QStringLiteral("canopyLauncherIcon")
                && parent->property("imageReady").toBool() ? 1 : 0;
    for (QQuickItem *child : parent->childItems())
        ready += countReadyLauncherImages(child);
    return ready;
}

// The previous tests centered dock tiles but never checked the actual
// launcher's image position relative to its own clickable app button.
// Inspect instantiated Qt Quick geometry at runtime, at each test size.
static bool launcherButtonImagesAreCentered(QQuickItem *item, int *checked) {
    if (!item)
        return false;
    if (item->objectName() == QStringLiteral("canopyLauncherAppButton")) {
        auto *icon = findVisualItem(item, QStringLiteral("canopyLauncherIcon"));
        if (!icon || !icon->isVisible() ||
            !icon->property("imageReady").toBool())
            return false;
        const QPointF imageOrigin = icon->mapToItem(item, QPointF(0, 0));
        const qreal imageMidX = imageOrigin.x() + icon->width() / 2;
        if (qAbs(imageMidX - item->width() / 2) > 0.75 ||
            imageOrigin.y() < -0.75 ||
            imageOrigin.y() + icon->height() > item->height() + 0.75)
            return false;
        ++*checked;
    }
    for (QQuickItem *child : item->childItems())
        if (!launcherButtonImagesAreCentered(child, checked))
            return false;
    return true;
}

static int countVisualItems(QQuickItem *parent, const QString &objectName) {
    if (!parent)
        return 0;
    int count = parent->objectName() == objectName ? 1 : 0;
    for (QQuickItem *child : parent->childItems())
        count += countVisualItems(child, objectName);
    return count;
}

static void collectVisualItems(QQuickItem *parent, const QString &objectName,
                               QVector<QQuickItem *> *found) {
    if (!parent)
        return;
    if (parent->objectName() == objectName)
        found->append(parent);
    for (QQuickItem *child : parent->childItems())
        collectVisualItems(child, objectName, found);
}

// The registered overlay must remain fail closed in the compiled shell:
// four named domains, unknown status, visible unavailable disclosures,
// disabled direct controls, and Settings only when the existing opt-in host
// launcher can actually handle it. This inspects the live QML scene, not
// source strings or a scratch harness.
static bool verifyQuickControlsScene(QQuickItem *content, bool settingsExpected,
                                     QString *reason) {
    auto *overlay = findVisualItem(content, QStringLiteral("canopyQuickControlsOverlay"));
    if (!overlay) {
        *reason = QStringLiteral("registered overlay missing from scene");
        return false;
    }
    if (overlay->property("opened").toBool() || overlay->isVisible()) {
        *reason = QStringLiteral("overlay must start hidden so approved desktop visuals stay unchanged");
        return false;
    }
    if (overlay->property("domainCount").toInt() != 4) {
        *reason = QStringLiteral("expected four quick-control domains");
        return false;
    }
    if (!QMetaObject::invokeMethod(overlay, "openControls", Qt::DirectConnection)) {
        *reason = QStringLiteral("openControls() not invokable");
        return false;
    }
    QCoreApplication::processEvents();
    if (!overlay->property("opened").toBool() || !overlay->isVisible()) {
        *reason = QStringLiteral("overlay did not open");
        return false;
    }
    QVector<QQuickItem *> rows;
    QVector<QQuickItem *> statuses;
    QVector<QQuickItem *> disclosures;
    QVector<QQuickItem *> settingsButtons;
    QVector<QQuickItem *> controlButtons;
    collectVisualItems(content, QStringLiteral("canopyQuickControlRow"), &rows);
    collectVisualItems(content, QStringLiteral("canopyQuickStatus"), &statuses);
    collectVisualItems(content, QStringLiteral("canopyQuickDisclosure"), &disclosures);
    collectVisualItems(content, QStringLiteral("canopyQuickSettingsButton"), &settingsButtons);
    collectVisualItems(content, QStringLiteral("canopyQuickControlButton"), &controlButtons);
    if (rows.size() != 4 || statuses.size() != 4 || disclosures.size() != 4
        || settingsButtons.size() != 4 || controlButtons.size() != 4) {
        *reason = QStringLiteral("incomplete instantiated control rows");
        return false;
    }
    int privilegedDisclosures = 0;
    for (QQuickItem *label : statuses) {
        if (label->property("text").toString()
            != QStringLiteral("Unknown — no host status")) {
            *reason = QStringLiteral("status was guessed instead of disclosed as unknown");
            return false;
        }
    }
    for (QQuickItem *label : disclosures) {
        const QString text = label->property("text").toString();
        if (!text.startsWith(QStringLiteral("Unavailable — "))) {
            *reason = QStringLiteral("unavailable control lacks a visible disclosure");
            return false;
        }
        if (text.contains(QStringLiteral("privileged host changes")))
            ++privilegedDisclosures;
    }
    if (privilegedDisclosures != 2) {
        *reason = QStringLiteral("Power and Session must disclose privileged host changes");
        return false;
    }
    for (QQuickItem *button : settingsButtons) {
        if (button->property("enabled").toBool() != settingsExpected) {
            *reason = QStringLiteral("Settings bridge state does not match the host adapter");
            return false;
        }
    }
    for (QQuickItem *button : controlButtons) {
        if (button->property("enabled").toBool()) {
            *reason = QStringLiteral("direct control enabled without a host action bridge");
            return false;
        }
    }
    if (!QMetaObject::invokeMethod(overlay, "closeControls", Qt::DirectConnection)) {
        *reason = QStringLiteral("closeControls() not invokable");
        return false;
    }
    QCoreApplication::processEvents();
    if (overlay->property("opened").toBool() || overlay->isVisible()) {
        *reason = QStringLiteral("overlay did not close");
        return false;
    }
    return true;
}

// An approved visual is never loaded from a guessed path or a replacement
// file. The manifest is source-controlled, and all nine external PNGs must
// match the exact source bytes before Qt is allowed to open the scene.
static bool verifyExactArtwork(const QString &dirPath, bool requireWave, QString *error) {
    const QDir root(dirPath);
    const QString canonicalRoot = root.canonicalPath();
    if (canonicalRoot.isEmpty() || QFileInfo(dirPath).isSymLink()) {
        *error = QStringLiteral("approved-art directory is missing or is a symlink");
        return false;
    }
    QFile manifest(QStringLiteral(":/Canopy/Classic/assets/approved/manifest.json"));
    if (!manifest.open(QIODevice::ReadOnly)) {
        *error = QStringLiteral("embedded approved-art manifest missing");
        return false;
    }
    QJsonParseError parseError;
    const QJsonDocument json = QJsonDocument::fromJson(manifest.readAll(), &parseError);
    if (parseError.error != QJsonParseError::NoError || !json.isObject()) {
        *error = QStringLiteral("approved-art manifest failed to parse");
        return false;
    }
    const QJsonObject config = json.object();
    const QJsonArray icons = config.value(QStringLiteral("icons")).toArray();
    const QJsonObject wallpaper = config.value(QStringLiteral("wallpaper")).toObject();
    if (config.value(QStringLiteral("schema_version")).toInt() != 1 ||
        icons.size() != 8 || wallpaper.isEmpty()) {
        *error = QStringLiteral("approved manifest must contain exactly eight icons and one wallpaper");
        return false;
    }
    QSet<QString> checkedPaths;
    auto verify = [&](const QJsonObject &item) -> bool {
        const QString relative = item.value(QStringLiteral("path")).toString();
        const QString sha = item.value(QStringLiteral("sha256")).toString();
        if (relative.isEmpty() || !relative.endsWith(QStringLiteral(".png")) ||
            relative.startsWith(QLatin1Char('/')) ||
            relative.contains(QLatin1Char('\\')) ||
            relative.split(QLatin1Char('/')).contains(QStringLiteral("..")) ||
            checkedPaths.contains(relative) || sha.size() != 64) {
            *error = QStringLiteral("invalid or duplicate approved-art manifest entry");
            return false;
        }
        checkedPaths.insert(relative);
        const QFileInfo asset(root.filePath(relative));
        if (!asset.exists() || !asset.isFile() || asset.isSymLink() ||
            asset.size() > 12'000'000 ||
            !asset.canonicalFilePath().startsWith(canonicalRoot + QLatin1Char('/'))) {
            *error = QStringLiteral("approved image is missing, unsafe or outside approved directory: ") + relative;
            return false;
        }
        QFile file(asset.absoluteFilePath());
        if (!file.open(QIODevice::ReadOnly)) {
            *error = QStringLiteral("cannot read approved art: ") + relative;
            return false;
        }
        const QByteArray digest = QCryptographicHash::hash(
            file.readAll(), QCryptographicHash::Sha256).toHex();
        if (digest != sha.toLatin1()) {
            *error = QStringLiteral("SHA-256 mismatch, refusing substitute: ") + relative;
            return false;
        }
        return true;
    };
    for (const QJsonValue &item : icons) {
        if (!item.isObject() || !verify(item.toObject()))
            return false;
    }
    if ((requireWave && !verify(wallpaper)) ||
        checkedPaths.size() != (requireWave ? 9 : 8)) {
        if (error->isEmpty())
            *error = QStringLiteral("incomplete approved-art set");
        return false;
    }
    return true;
}

// Local photo only; never download artwork, follow symlinks, or decode an
// unbounded image. QImageReader checks headers without allocating a bitmap.
static bool verifyLandscapeWallpaper(const QString &filePath,
                                     QString *canonicalPath, QString *error) {
    const QFileInfo file(filePath);
    if (!file.exists() || !file.isFile() || file.isSymLink() ||
        file.size() <= 0 || file.size() > 24'000'000) {
        *error = QStringLiteral("wallpaper must be a regular local image (up to 24 MB)");
        return false;
    }
    const QString extension = file.suffix().toLower();
    if (extension != QStringLiteral("png") &&
        extension != QStringLiteral("jpg") &&
        extension != QStringLiteral("jpeg")) {
        *error = QStringLiteral("wallpaper must be PNG or JPEG");
        return false;
    }
    const QString canonical = file.canonicalFilePath();
    if (canonical.isEmpty()) {
        *error = QStringLiteral("wallpaper path is invalid");
        return false;
    }
    QImageReader reader(canonical);
    const QByteArray format = reader.format().toLower();
    if (!reader.canRead() ||
        (format != "png" && format != "jpeg" && format != "jpg")) {
        *error = QStringLiteral("wallpaper content is not a readable PNG/JPEG");
        return false;
    }
    const QSize size = reader.size();
    if (!size.isValid() || size.width() < 1920 || size.height() < 1080 ||
        size.width() > 8192 || size.height() > 8192 ||
        qint64(size.width()) * size.height() > 32'000'000 ||
        double(size.width()) / size.height() < 1.45 ||
        double(size.width()) / size.height() > 2.15) {
        *error = QStringLiteral("wallpaper must be landscape, at least 1920x1080, at most 32 megapixels");
        return false;
    }
    *canonicalPath = canonical;
    return true;
}

int main(int argc, char *argv[]) {
    QGuiApplication app(argc, argv);
    QGuiApplication::setApplicationDisplayName(QStringLiteral("Canopy Classic Spike"));
    const QStringList args = QCoreApplication::arguments();
    // Native Linux app launching is opt-in. Default preview visuals, dock
    // geometry and screenshot contracts are unchanged when the flag is absent.
    const bool enableSystemApps = args.contains(QStringLiteral("--enable-system-apps"));
    SystemAppLauncher systemLauncher(enableSystemApps);
    WindowActivationState activationState;
    const QString activationBackend = activationBackendId();
    activationState.applySnapshot(
        hostActivationSnapshot(systemLauncher, activationBackend, 1));
    const int activationSnapshotIndex = args.indexOf(
        QStringLiteral("--window-activation-snapshot"));
    if (activationSnapshotIndex >= 0) {
        if (activationSnapshotIndex + 1 >= args.size()
                || args.at(activationSnapshotIndex + 1).startsWith(QLatin1Char('-'))) {
            qCritical() << "CANOPY_ACTIVATION_SNAPSHOT_FAIL: missing path";
            return 2;
        }
        if (loadActivationSnapshotFile(
                    activationState, args.at(activationSnapshotIndex + 1))) {
            qInfo() << "CANOPY_ACTIVATION_SNAPSHOT_APPLIED";
        } else {
            qWarning() << "CANOPY_ACTIVATION_SNAPSHOT_REJECTED_FAIL_CLOSED";
        }
    } else if (activationBackend.isEmpty()) {
        qWarning() << "CANOPY_ACTIVATION_BACKEND_UNKNOWN_FAIL_CLOSED";
    }
    const bool launcherFixture = args.contains(QStringLiteral("--self-test-launcher-launch-fixture"));
    if (args.contains(QStringLiteral("--self-test-system-apps-capability"))) {
#ifdef CANOPY_HAVE_GIO
        qInfo() << "CANOPY_GIO_ENABLED";
#else
        qInfo() << "CANOPY_GIO_DISABLED";
#endif
        return 0;
    }
    if (args.contains(QStringLiteral("--self-test-system-apps-fixture"))) {
        // CI supplies a disposable XDG_DATA_HOME with a nemo.desktop whose
        // Exec touches a marker. This exercises the real GIO launch path and
        // never opens any of the current user's applications.
        if (!enableSystemApps || !systemLauncher.canLaunch(QStringLiteral("Files"))
            || !systemLauncher.launch(QStringLiteral("Files"))) {
            qCritical() << "SYSTEM_APP_LAUNCH_FIXTURE_FAIL: GIO desktop launch unsuccessful";
            return 1;
        }
        qInfo() << "SYSTEM_APP_LAUNCH_FIXTURE_PASS: GIO accepted isolated desktop entry";
        return 0;
    }
    if (args.contains(QStringLiteral("--self-test-system-apps"))) {
        // Never executes a valid desktop app. Prove shell text, paths, desktop
        // IDs and free-form input cannot cross the fixed eight-name allowlist.
        const QStringList denied = {
            QStringLiteral("sh -c 'touch /tmp/canopy-bad'"),
            QStringLiteral("../firefox.desktop"),
            QStringLiteral("Browser;echo hacked"),
            QStringLiteral("firefox.desktop"),
            QStringLiteral(""),
            QStringLiteral("Unknown")
        };
        for (const QString &value : denied) {
            if (systemLauncher.canLaunch(value) || systemLauncher.launch(value)) {
                qCritical() << "SYSTEM_APP_LAUNCH_TEST_FAIL: arbitrary launch accepted";
                return 1;
            }
        }
        if (!enableSystemApps && (systemLauncher.canLaunch(QStringLiteral("Browser"))
                                  || systemLauncher.launch(QStringLiteral("Browser")))) {
            qCritical() << "SYSTEM_APP_LAUNCH_TEST_FAIL: launch not opt-in";
            return 1;
        }
        qInfo() << "SYSTEM_APP_LAUNCH_TEST_PASS: unknown or dangerous actions refused, no application executed";
        return 0;
    }
    const int approvedIndex = args.indexOf(QStringLiteral("--approved-art-dir"));
    const bool approvedMode = approvedIndex >= 0;
    const bool framingReviewMode = args.contains(QStringLiteral("--icon-framing-review"));
    if (framingReviewMode && !approvedMode) {
        qCritical() << "ICON_FRAMING_REVIEW_FAIL: exact SHA-locked approved art required";
        return 2;
    }
    const bool requireApproved = args.contains(QStringLiteral("--self-test-approved"));
    const int landscapeIndex = args.indexOf(QStringLiteral("--landscape-wallpaper"));
    const bool landscapeMode = landscapeIndex >= 0;
    const int terminalRefinementIndex = args.indexOf(QStringLiteral("--terminal-refinement"));
    QString landscapePath;
    if (landscapeMode) {
        if (landscapeIndex + 1 >= args.size() ||
            args.at(landscapeIndex + 1).startsWith(QLatin1Char('-'))) {
            qCritical() << "LANDSCAPE_WALLPAPER_FAIL: missing --landscape-wallpaper PATH";
            return 2;
        }
        QString error;
        if (!verifyLandscapeWallpaper(args.at(landscapeIndex + 1),
                                      &landscapePath, &error)) {
            qCritical().noquote() << "LANDSCAPE_WALLPAPER_FAIL:" << error;
            return 3;
        }
        qInfo() << "CANOPY_LANDSCAPE_WALLPAPER_VERIFIED: local PNG/JPEG";
    }
    if (requireApproved && !approvedMode) {
        qCritical() << "APPROVED_ART_FAIL: --self-test-approved requires --approved-art-dir";
        return 2;
    }
    QString approvedRoot;
    if (approvedMode) {
        if (approvedIndex + 1 >= args.size() || args.at(approvedIndex + 1).startsWith(QLatin1Char('-'))) {
            qCritical() << "APPROVED_ART_FAIL: missing --approved-art-dir PATH";
            return 2;
        }
        const QString requested = args.at(approvedIndex + 1);
        QString error;
        if (!verifyExactArtwork(requested, !landscapeMode, &error)) {
            qCritical().noquote() << "APPROVED_ART_FAIL:" << error;
            return 3;
        }
        approvedRoot = QDir(requested).canonicalPath();
        qInfo() << (landscapeMode ?
            "CANOPY_APPROVED_ART_VERIFIED: eight exact PNG icons; landscape wallpaper separately checked" :
            "CANOPY_APPROVED_ART_VERIFIED: eight exact PNG icons and legacy blue wave");
    }
    // The new art is a proposal only; verify it separately and never
    // overwrite or bypass the eight SHA-locked, user-approved master PNGs.
    QString terminalCandidatePath;
    if (terminalRefinementIndex >= 0) {
        if (!approvedMode || terminalRefinementIndex + 1 >= args.size() ||
            args.at(terminalRefinementIndex + 1).startsWith(QLatin1Char('-'))) {
            qCritical() << "TERMINAL_REFINEMENT_FAIL: requires approved art and a PNG path";
            return 2;
        }
        const QFileInfo candidate(args.at(terminalRefinementIndex + 1));
        if (!candidate.exists() || !candidate.isFile() || candidate.isSymLink() ||
            candidate.size() < 256 || candidate.size() > 5'000'000) {
            qCritical() << "TERMINAL_REFINEMENT_FAIL: unsafe or missing PNG";
            return 3;
        }
        const QString filePath = candidate.canonicalFilePath();
        QImageReader reader(filePath);
        const QSize dimensions = reader.size();
        if (!reader.canRead() || reader.format().toLower() != "png" ||
            !dimensions.isValid() || dimensions.width() < 256 ||
            dimensions.width() > 2048 || dimensions.height() != dimensions.width()) {
            qCritical() << "TERMINAL_REFINEMENT_FAIL: expected square 256-2048px PNG";
            return 3;
        }
        const QImage image = reader.read();
        if (image.isNull() || !image.hasAlphaChannel() ||
            image.pixelColor(0, 0).alpha() > 32 ||
            image.pixelColor(image.width() - 1, 0).alpha() > 32 ||
            image.pixelColor(0, image.height() - 1).alpha() > 32 ||
            image.pixelColor(image.width() - 1,
                             image.height() - 1).alpha() > 32) {
            qCritical() << "TERMINAL_REFINEMENT_FAIL: image lacks transparent corners";
            return 3;
        }
        terminalCandidatePath = filePath;
        qInfo() << "CANOPY_TERMINAL_CANDIDATE_VERIFIED: optional, Terminal only";
    }
    QQmlApplicationEngine engine;
    if (approvedMode) {
        // Source PNGs were SHA-verified above; transform copies IN MEMORY
        // only. The files and their immutable manifest remain unchanged.
        QString roundedError;
        // The dock is locked to the existing original full-fit rendering.
        // Experimental optical adjustments are isolated to a DIFFERENT
        // QQuickImageProvider, instantiated only for an explicit review.
        auto *roundedIcons = new RoundedDockIconProvider(
            approvedRoot, terminalCandidatePath, false, &roundedError);
        if (!roundedIcons->isValid() || !roundedIcons->allCornersClipped()) {
            qCritical().noquote() << "APPROVED_ART_FAIL: rounded dock rendering:"
                                   << roundedError;
            delete roundedIcons;
            return 3;
        }
        engine.addImageProvider(QStringLiteral("canopy-dock"), roundedIcons);
        qInfo() << "CANOPY_ROUNDED_DOCK_VERIFIED: eight original icons, padded, alpha-clipped";
        if (framingReviewMode) {
            QString reviewError;
            auto *launcherReviewIcons = new RoundedDockIconProvider(
                approvedRoot, terminalCandidatePath, true, &reviewError);
            if (!launcherReviewIcons->isValid() ||
                !launcherReviewIcons->allCornersClipped()) {
                qCritical().noquote()
                    << "ICON_FRAMING_REVIEW_FAIL: launcher-only rendering:"
                    << reviewError;
                delete launcherReviewIcons;
                return 3;
            }
            engine.addImageProvider(QStringLiteral("canopy-launcher-review"),
                                    launcherReviewIcons);
            qInfo() << "ICON_FRAMING_REVIEW_ACTIVE: launcher-only source-content"
                       " review, dock provider and original masters unchanged;"
                       " owner visual approval NOT granted";
        }
    }
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopyWindowActivationState"), &activationState);
    QQmlComponent activationComponent(
        &engine, QUrl(QStringLiteral(
            "qrc:/Canopy/Classic/WindowActivationIndicators.qml")));
    if (activationComponent.isError()) {
        qCritical() << "WINDOW_ACTIVATION_ADAPTER_FAIL: QML component error";
        return 1;
    }
    QObject *activationAdapter = activationComponent.create();
    if (!activationAdapter) {
        qCritical() << "WINDOW_ACTIVATION_ADAPTER_FAIL: no QML instance";
        return 1;
    }
    activationAdapter->setParent(&engine);
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopyWindowActivation"), activationAdapter);
    qInfo() << "WINDOW_ACTIVATION_ADAPTER_LOADED";

    engine.rootContext()->setContextProperty(QStringLiteral("canopyApprovedMode"), approvedMode);
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopySystemLaunchEnabled"), enableSystemApps);
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopySystemLauncher"), &systemLauncher);
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopyIconFramingReview"), framingReviewMode);
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopyLandscapeWallpaperUrl"),
        landscapeMode ? QUrl::fromLocalFile(landscapePath).toString() : QString());
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopyApprovedIconBase"),
        approvedMode ? QUrl::fromLocalFile(approvedRoot + QStringLiteral("/icons/")).toString()
                     : QString());
    engine.rootContext()->setContextProperty(
        QStringLiteral("canopyApprovedWallpaperUrl"),
        approvedMode ? QUrl::fromLocalFile(
            approvedRoot + QStringLiteral("/wallpaper/canopy-wave-preview.png")).toString()
                     : QString());
    engine.load(QUrl(QStringLiteral("qrc:/Canopy/Classic/Main.qml")));
    if (engine.rootObjects().isEmpty())
        return 1;
    auto *window = qobject_cast<QQuickWindow *>(engine.rootObjects().constFirst());
    if (!window || !window->isVisible()) {
        qCritical() << "Canopy Classic: QML root did not create a visible window";
        return 1;
    }
    qInfo() << "CANOPY_CLASSIC_WINDOW_READY";
    QObject::connect(&activationState, &WindowActivationState::stateChanged,
                     &app, [window, &activationState, activationAdapter]() {
        updateDockActivationProperties(
            window->contentItem(), activationState, activationAdapter);
    });
    updateDockActivationProperties(
        window->contentItem(), activationState, activationAdapter);

    // Register the PR #582 overlay in the compiled shell without changing
    // Main.qml or any approved QML/asset bytes. It is created hidden, filled
    // to the window and raised above the existing chrome; the only opener is
    // a local host shortcut, mirroring the existing host-side dock bridges.
    QShortcut *quickControlsShortcut = nullptr;
    QQuickItem *quickControlsOverlay = nullptr;
    {
        QQmlComponent component(&engine,
            QUrl(QStringLiteral("qrc:/Canopy/Classic/QuickControlsOverlay.qml")));
        if (!component.isReady() || component.isError()) {
            qCritical().noquote() << "QUICK_CONTROLS_FAIL: QML component:"
                                  << component.errorString();
            return 1;
        }
        QVariantMap initial;
        initial.insert(QStringLiteral("width"), window->contentItem()->width());
        initial.insert(QStringLiteral("height"), window->contentItem()->height());
        quickControlsOverlay = qobject_cast<QQuickItem *>(
            component.createWithInitialProperties(initial, engine.rootContext()));
        if (!quickControlsOverlay) {
            qCritical().noquote() << "QUICK_CONTROLS_FAIL: could not instantiate overlay:"
                                  << component.errorString();
            return 1;
        }
        auto *content = window->contentItem();
        quickControlsOverlay->setParent(content);
        quickControlsOverlay->setParentItem(content);
        quickControlsOverlay->setZ(100);
        const auto syncGeometry = [quickControlsOverlay, content]() {
            quickControlsOverlay->setWidth(content->width());
            quickControlsOverlay->setHeight(content->height());
        };
        QObject::connect(content, &QQuickItem::widthChanged,
                         quickControlsOverlay, syncGeometry);
        QObject::connect(content, &QQuickItem::heightChanged,
                         quickControlsOverlay, syncGeometry);
        quickControlsShortcut = new QShortcut(
            QKeySequence(QStringLiteral("Ctrl+Alt+Q")), window);
        QObject::connect(quickControlsShortcut, &QShortcut::activated,
                         quickControlsOverlay, [quickControlsOverlay]() {
            QMetaObject::invokeMethod(quickControlsOverlay, "toggleControls",
                                      Qt::DirectConnection);
        });
        qInfo() << "CANOPY_QUICK_CONTROLS_REGISTERED: hidden until requested, "
                   "no host control bridge, no visual asset changes";
    }

    if (enableSystemApps) {
        // Dock integration without editing the frozen dock QML bytes: wire the
        // existing DockTile `activated` signal to the host-owned GIO service.
        static const QStringList dockNames = {
            QStringLiteral("Browser"), QStringLiteral("Mail"),
            QStringLiteral("Files"), QStringLiteral("Calendar"),
            QStringLiteral("Photos"), QStringLiteral("Music"),
            QStringLiteral("Terminal"), QStringLiteral("Settings"),
            QStringLiteral("Trash")
        };
        for (const QString &name : dockNames) {
            // Files, Browser and Mail are wired to the same host service
            // below, with a fail-closed status path; other tiles keep their
            // original direct connection.
            if (name == QStringLiteral("Files") || name == QStringLiteral("Browser"))
                continue;
            if (name == QStringLiteral("Mail"))
                continue;
            if (name != QStringLiteral("Trash"))
                continue;  // approved names use the intent gate below
            if (auto *tile = findDockTile(window->contentItem(), name))
                QObject::connect(tile, SIGNAL(activated(QString)),
                                 &systemLauncher, SLOT(launch(QString)));
        }
        qInfo() << "CANOPY_SYSTEM_APP_DOCK_CONNECTED: opt-in, fixed allowlist only";
    }


        // Connect the EXISTING Files dock interaction (its frozen QML
        // `activated("Files")` signal) to real desktop behavior. No QML,
        // artwork, dock geometry or color is changed: this is a host-side
        // adapter over the single SystemAppLauncher service.
        auto *filesLaunchTile = findDockTile(window->contentItem(),
                                              QStringLiteral("Files"));
        auto *filesStatusOverlay = findVisualItem(
            window->contentItem(), QStringLiteral("canopyApplicationLauncher"));
        if (filesLaunchTile) {
            auto *filesBridge = new FilesDockLaunchBridge(
                systemLauncher, activationState,
                filesStatusOverlay, &app);
            QObject::connect(filesLaunchTile, SIGNAL(activated(QString)),
                             filesBridge, SLOT(activate(QString)));
            qInfo() << "CANOPY_FILES_DOCK_NATIVE_LAUNCH_CONNECTED";
        }

        // Same host-side adapter for the existing Browser dock interaction.
        // No QML/asset edits: the frozen `activated("Browser")` signal alone is
        // connected, and Browser is removed from the direct-connect loop above.
        auto *browserLaunchTile = findDockTile(window->contentItem(),
                                                QStringLiteral("Browser"));
        auto *browserStatusOverlay = findVisualItem(
            window->contentItem(), QStringLiteral("canopyApplicationLauncher"));
        if (browserLaunchTile) {
            auto *browserBridge = new BrowserDockLaunchBridge(
                systemLauncher, activationState,
                browserStatusOverlay, &app);
            QObject::connect(browserLaunchTile, SIGNAL(activated(QString)),
                             browserBridge, SLOT(activate(QString)));
            qInfo() << "CANOPY_BROWSER_DOCK_NATIVE_LAUNCH_CONNECTED";
        }

        // Same host-side adapter for the existing Mail dock interaction.
        // Mail is present in the approved eight-icon dock; the frozen QML
        // `activated("Mail")` signal alone is connected and Mail is removed
        // from the direct-connect loop above. No QML or asset bytes change.
        auto *mailLaunchTile = findDockTile(window->contentItem(),
                                            QStringLiteral("Mail"));
        auto *mailStatusOverlay = findVisualItem(
            window->contentItem(), QStringLiteral("canopyApplicationLauncher"));
        if (mailLaunchTile) {
            auto *mailBridge = new MailDockLaunchBridge(
                systemLauncher, activationState,
                mailStatusOverlay, &app);
            QObject::connect(mailLaunchTile, SIGNAL(activated(QString)),
                             mailBridge, SLOT(activate(QString)));
            qInfo() << "CANOPY_MAIL_DOCK_NATIVE_LAUNCH_CONNECTED";
        }

        auto *intentStatusOverlay = findVisualItem(
            window->contentItem(), QStringLiteral("canopyApplicationLauncher"));
        auto *intentBridge = new IntentDockBridge(
            systemLauncher, activationState, intentStatusOverlay, &app);
        static const QStringList gatedDockNames = {
            QStringLiteral("Calendar"), QStringLiteral("Photos"),
            QStringLiteral("Music"), QStringLiteral("Terminal"),
            QStringLiteral("Settings")
        };
        for (const QString &name : gatedDockNames) {
            if (auto *tile = findDockTile(window->contentItem(), name)) {
                QObject::connect(tile, SIGNAL(activated(QString)),
                                 intentBridge, SLOT(activate(QString)));
                qInfo() << "CANOPY_INTENT_DOCK_CONNECTED" << name;
            }
        }
    const bool activationFixture = args.contains(
        QStringLiteral("--self-test-window-activation-fixture"));
    if (activationFixture) {
        // Trusted host snapshot: running + active + explicit grant.
        const QByteArray trusted = R"JSON({
          "schema": 1, "backend": "x11", "negotiation": "SUPPORTED",
          "sequence": 10, "launcherEnabled": true,
          "installed": ["Files"],
          "owners": [{"pid": 4242, "app_id": "Files"}],
          "grants": [["Canopy", "Files"]],
          "focus": {"app_id": "Files", "window_id": 7,
                    "serial": 1, "status": "GRANTED"}
        })JSON";
        auto *filesTile = findDockTile(window->contentItem(),
                                       QStringLiteral("Files"));
        auto *status = findVisualItem(
            window->contentItem(), QStringLiteral("canopyLauncherStatus"));
        if (!applyActivationJson(activationState, trusted)
                || !filesTile || !status
                || activationState.status() != QStringLiteral("READY")) {
            qCritical() << "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: trusted snapshot";
            return 1;
        }
        QCoreApplication::processEvents();
        if (!tileProperty(filesTile, QStringLiteral("windowRunning")).toBool()
                || !tileProperty(filesTile, QStringLiteral("windowActive")).toBool()
                || tileProperty(filesTile, QStringLiteral("activationIntent")).toString()
                        != QStringLiteral("FOCUS")
                || !activationAdapter->property("indicatorsAvailable").toBool()) {
            qCritical() << "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: indicators";
            return 1;
        }
        const QQmlProperty trustedDescription(
            filesTile, QStringLiteral("Accessible.description"),
            QQmlEngine::contextForObject(filesTile));
        if (!trustedDescription.isValid()
                || !trustedDescription.read().toString().contains(
                       QStringLiteral("active window"))) {
            qCritical() << "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: accessibility disclosure";
            return 1;
        }
        qInfo() << "SELF_TEST_PASS: dock running and active indicators reflect trusted snapshot";
        if (!QMetaObject::invokeMethod(
                    filesTile, "activated", Qt::DirectConnection,
                    Q_ARG(QString, QStringLiteral("Files")))) {
            qCritical() << "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: activation";
            return 1;
        }
        QCoreApplication::processEvents();
        if (!status->property("text").toString().contains(
                    QStringLiteral("focus is unavailable"))) {
            qCritical() << "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: focus disclosed";
            return 1;
        }
        qInfo() << "SELF_TEST_PASS: dock activation intent reaches host gate without false focus";

        // Closed state: no owners and no focus for the same app.
        const QByteArray closed = R"JSON({
          "schema": 1, "backend": "x11", "negotiation": "SUPPORTED",
          "sequence": 11, "launcherEnabled": true,
          "installed": ["Files"], "owners": [], "grants": []
        })JSON";
        if (!applyActivationJson(activationState, closed)) {
            qCritical() << "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: closed snapshot";
            return 1;
        }
        QCoreApplication::processEvents();
        if (tileProperty(filesTile, QStringLiteral("windowRunning")).toBool()
                || tileProperty(filesTile, QStringLiteral("windowActive")).toBool()
                || tileProperty(filesTile, QStringLiteral("activationIntent")).toString()
                        != QStringLiteral("LAUNCH")) {
            qCritical() << "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: closed state";
            return 1;
        }
        qInfo() << "SELF_TEST_PASS: closed snapshot clears running and active indicators";

        // Unknown backend must clear every indicator and remove trust.
        const QByteArray invalid = R"JSON({
          "schema": 1, "backend": "unknown", "negotiation": "SUPPORTED",
          "sequence": 12, "launcherEnabled": true,
          "installed": ["Files"],
          "owners": [{"pid": 4242, "app_id": "Files"}], "grants": []
        })JSON";
        QCoreApplication::processEvents();
        if (applyActivationJson(activationState, invalid)
                || activationState.status() != QStringLiteral("UNAVAILABLE")
                || tileProperty(filesTile, QStringLiteral("activationAvailable")).toBool()
                || tileProperty(filesTile, QStringLiteral("windowRunning")).toBool()
                || tileProperty(filesTile, QStringLiteral("activationIntent")).toString()
                        != QStringLiteral("REJECT")
                || activationAdapter->property("indicatorsAvailable").toBool()) {
            qCritical() << "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: fail closed";
            return 1;
        }
        const QQmlProperty clearedDescription(
            filesTile, QStringLiteral("Accessible.description"),
            QQmlEngine::contextForObject(filesTile));
        if (!clearedDescription.isValid()
                || !clearedDescription.read().toString().contains(
                       QStringLiteral("window activation state unavailable"))) {
            qCritical() << "WINDOW_ACTIVATION_HOST_FIXTURE_FAIL: cleared disclosure";
            return 1;
        }
        qInfo() << "SELF_TEST_PASS: untrusted snapshot clears all indicators";
        qInfo() << "WINDOW_ACTIVATION_HOST_SELF_TEST_PASS"
                << "running=ok active=ok closed=ok fail_closed=ok";
        QTimer::singleShot(0, &app, &QCoreApplication::quit);
    }
    if (args.contains(QStringLiteral("--self-test-quick-controls"))) {
        const bool settingsExpected =
            enableSystemApps && systemLauncher.canLaunch(QStringLiteral("Settings"));
        if (!quickControlsShortcut || !quickControlsOverlay) {
            qCritical() << "QUICK_CONTROLS_FIXTURE_FAIL: overlay or opener missing";
            return 1;
        }
        // Trigger the real host shortcut connection, not the QML function
        // directly, so the compiled-shell opener is part of the evidence.
        if (!QMetaObject::invokeMethod(quickControlsShortcut, "activated",
                                       Qt::DirectConnection)) {
            qCritical() << "QUICK_CONTROLS_FIXTURE_FAIL: opener not invokable";
            return 1;
        }
        QCoreApplication::processEvents();
        if (!quickControlsOverlay->property("opened").toBool()
            || !quickControlsOverlay->isVisible()) {
            qCritical() << "QUICK_CONTROLS_FIXTURE_FAIL: opener did not open overlay";
            return 1;
        }
        if (!QMetaObject::invokeMethod(quickControlsOverlay, "closeControls",
                                       Qt::DirectConnection)) {
            qCritical() << "QUICK_CONTROLS_FIXTURE_FAIL: overlay close failed";
            return 1;
        }
        QCoreApplication::processEvents();
        QString reason;
        if (!verifyQuickControlsScene(window->contentItem(), settingsExpected,
                                      &reason)) {
            qCritical().noquote() << "QUICK_CONTROLS_FIXTURE_FAIL:" << reason;
            return 1;
        }
        qInfo() << "SELF_TEST_PASS: quick controls registered in compiled shell";
        qInfo() << "QUICK_CONTROLS_FIXTURE_PASS: opener wired, four domains fail closed,"
                   " approved visuals unchanged";
        QTimer::singleShot(0, &app, &QCoreApplication::quit);
    }
    if (launcherFixture) {
        // Drive the actual QML overlay's choose("Files") path. CI supplies a
        // disposable GIO desktop entry and checks its marker, not a real app.
        if (!enableSystemApps) {
            qCritical() << "LAUNCHER_LAUNCH_FIXTURE_FAIL: native apps not enabled";
            return 1;
        }
        auto *overlay = findVisualItem(
            window->contentItem(), QStringLiteral("canopyApplicationLauncher"));
        if (!overlay || !QMetaObject::invokeMethod(
                overlay, "choose", Qt::DirectConnection,
                Q_ARG(QString, QStringLiteral("Files")))
            || overlay->property("opened").toBool()) {
            qCritical() << "LAUNCHER_LAUNCH_FIXTURE_FAIL: QML launcher activation failed";
            return 1;
        }
        qInfo() << "SELF_TEST_PASS: QML launcher choose() activated native GIO app";
        qInfo() << "LAUNCHER_LAUNCH_FIXTURE_PASS: QML launcher activation verified";
        QTimer::singleShot(0, &app, &QCoreApplication::quit);
    }
    const bool filesDockStatusFixture = args.contains(
        QStringLiteral("--self-test-files-dock-status"));
    const bool filesDockLaunchFixture = args.contains(
        QStringLiteral("--self-test-files-dock-fixture"));
    if (filesDockStatusFixture || filesDockLaunchFixture) {
        if (!enableSystemApps) {
            qCritical() << "FILES_DOCK_FIXTURE_FAIL: native launch not enabled";
            return 1;
        }
        const bool canLaunchFiles =
            systemLauncher.canLaunch(QStringLiteral("Files"));
        if (filesDockStatusFixture && canLaunchFiles) {
            qCritical() << "FILES_DOCK_FIXTURE_FAIL: status case needs no file manager";
            return 1;
        }
        if (filesDockLaunchFixture && !canLaunchFiles) {
            qCritical() << "FILES_DOCK_FIXTURE_FAIL: GIO file manager unavailable";
            return 1;
        }
        auto *filesTile = findDockTile(
            window->contentItem(), QStringLiteral("Files"));
        auto *filesOverlay = findVisualItem(
            window->contentItem(), QStringLiteral("canopyApplicationLauncher"));
        auto *filesStatus = findVisualItem(
            window->contentItem(), QStringLiteral("canopyLauncherStatus"));
        if (!filesTile || !filesOverlay || !filesStatus) {
            qCritical() << "FILES_DOCK_FIXTURE_FAIL: frozen dock or status footer missing";
            return 1;
        }
        const QString initialStatus = filesStatus->property("text").toString();
        // A hostile lookalike label must change neither launcher nor status.
        if (!QMetaObject::invokeMethod(
                filesTile, "activated", Qt::DirectConnection,
                Q_ARG(QString, QStringLiteral("Browser;echo bad")))) {
            qCritical() << "FILES_DOCK_FIXTURE_FAIL: signal not invokable";
            return 1;
        }
        QCoreApplication::processEvents();
        if (filesOverlay->property("opened").toBool()
            || filesStatus->property("text").toString() != initialStatus) {
            qCritical() << "FILES_DOCK_FIXTURE_FAIL: unknown action accepted";
            return 1;
        }
        if (!QMetaObject::invokeMethod(
                filesTile, "activated", Qt::DirectConnection,
                Q_ARG(QString, QStringLiteral("Files")))) {
            qCritical() << "FILES_DOCK_FIXTURE_FAIL: dock activation failed";
            return 1;
        }
        QCoreApplication::processEvents();
        if (filesDockStatusFixture) {
            const QString shown = filesStatus->property("text").toString();
            if (!filesOverlay->property("opened").toBool()
                || !shown.contains(QStringLiteral("Files could not be launched"))) {
                qCritical() << "FILES_DOCK_FIXTURE_FAIL: refusal not visible to user";
                return 1;
            }
            qInfo() << "FILES_DOCK_STATUS_FIXTURE_PASS: refusal visible in launcher footer";
        } else {
            if (filesOverlay->property("opened").toBool()
                || filesStatus->property("text").toString() != initialStatus) {
                qCritical() << "FILES_DOCK_FIXTURE_FAIL: native launch reported a refusal";
                return 1;
            }
            qInfo() << "SELF_TEST_PASS: Files dock activated native GIO launch";
            qInfo() << "FILES_DOCK_LAUNCH_FIXTURE_PASS: dock signal reached GIO service";
        }
        QTimer::singleShot(0, &app, &QCoreApplication::quit);
    }
    const bool browserDockStatusFixture = args.contains(
        QStringLiteral("--self-test-browser-dock-status"));
    const bool browserDockLaunchFixture = args.contains(
        QStringLiteral("--self-test-browser-dock-fixture"));
    if (browserDockStatusFixture || browserDockLaunchFixture) {
        if (!enableSystemApps) {
            qCritical() << "BROWSER_DOCK_FIXTURE_FAIL: native launch not enabled";
            return 1;
        }
        const bool canLaunchBrowser =
            systemLauncher.canLaunch(QStringLiteral("Browser"));
        if (browserDockStatusFixture && canLaunchBrowser) {
            qCritical() << "BROWSER_DOCK_FIXTURE_FAIL: status case needs no browser";
            return 1;
        }
        if (browserDockLaunchFixture && !canLaunchBrowser) {
            qCritical() << "BROWSER_DOCK_FIXTURE_FAIL: GIO browser unavailable";
            return 1;
        }
        auto *browserTile = findDockTile(
            window->contentItem(), QStringLiteral("Browser"));
        auto *browserOverlay = findVisualItem(
            window->contentItem(), QStringLiteral("canopyApplicationLauncher"));
        auto *browserStatus = findVisualItem(
            window->contentItem(), QStringLiteral("canopyLauncherStatus"));
        if (!browserTile || !browserOverlay || !browserStatus) {
            qCritical() << "BROWSER_DOCK_FIXTURE_FAIL: frozen dock or status footer missing";
            return 1;
        }
        const QString initialStatus = browserStatus->property("text").toString();
        // A hostile lookalike label must change neither launcher nor status.
        if (!QMetaObject::invokeMethod(
                browserTile, "activated", Qt::DirectConnection,
                Q_ARG(QString, QStringLiteral("Browser;echo bad")))) {
            qCritical() << "BROWSER_DOCK_FIXTURE_FAIL: signal not invokable";
            return 1;
        }
        QCoreApplication::processEvents();
        if (browserOverlay->property("opened").toBool()
            || browserStatus->property("text").toString() != initialStatus) {
            qCritical() << "BROWSER_DOCK_FIXTURE_FAIL: unknown action accepted";
            return 1;
        }
        if (!QMetaObject::invokeMethod(
                browserTile, "activated", Qt::DirectConnection,
                Q_ARG(QString, QStringLiteral("Browser")))) {
            qCritical() << "BROWSER_DOCK_FIXTURE_FAIL: dock activation failed";
            return 1;
        }
        QCoreApplication::processEvents();
        if (browserDockStatusFixture) {
            const QString shown = browserStatus->property("text").toString();
            if (!browserOverlay->property("opened").toBool()
                || !shown.contains(QStringLiteral("Browser could not be launched"))) {
                qCritical() << "BROWSER_DOCK_FIXTURE_FAIL: refusal not visible to user";
                return 1;
            }
            qInfo() << "BROWSER_DOCK_STATUS_FIXTURE_PASS: refusal visible in launcher footer";
        } else {
            if (browserOverlay->property("opened").toBool()
                || browserStatus->property("text").toString() != initialStatus) {
                qCritical() << "BROWSER_DOCK_FIXTURE_FAIL: native launch reported a refusal";
                return 1;
            }
            qInfo() << "SELF_TEST_PASS: Browser dock activated native GIO launch";
            qInfo() << "BROWSER_DOCK_LAUNCH_FIXTURE_PASS: dock signal reached GIO service";
        }
        QTimer::singleShot(0, &app, &QCoreApplication::quit);
    }
    const bool mailDockStatusFixture = args.contains(
        QStringLiteral("--self-test-mail-dock-status"));
    const bool mailDockLaunchFixture = args.contains(
        QStringLiteral("--self-test-mail-dock-fixture"));
    if (mailDockStatusFixture || mailDockLaunchFixture) {
        if (!enableSystemApps) {
            qCritical() << "MAIL_DOCK_FIXTURE_FAIL: native launch not enabled";
            return 1;
        }
        // Mail is a tile only in the approved eight-icon dock. Requesting it
        // explicitly keeps the frozen visual source untouched.
        if (!approvedMode) {
            qCritical() << "MAIL_DOCK_FIXTURE_FAIL: approved dock required";
            return 1;
        }
        const bool canLaunchMail = systemLauncher.canLaunch(QStringLiteral("Mail"));
        if (mailDockStatusFixture && canLaunchMail) {
            qCritical() << "MAIL_DOCK_FIXTURE_FAIL: status case needs no mail app";
            return 1;
        }
        if (mailDockLaunchFixture && !canLaunchMail) {
            qCritical() << "MAIL_DOCK_FIXTURE_FAIL: GIO mail app unavailable";
            return 1;
        }
        auto *mailTile = findDockTile(
            window->contentItem(), QStringLiteral("Mail"));
        auto *mailOverlay = findVisualItem(
            window->contentItem(), QStringLiteral("canopyApplicationLauncher"));
        auto *mailStatus = findVisualItem(
            window->contentItem(), QStringLiteral("canopyLauncherStatus"));
        if (!mailTile || !mailOverlay || !mailStatus) {
            qCritical() << "MAIL_DOCK_FIXTURE_FAIL: frozen dock or status footer missing";
            return 1;
        }
        const QString initialStatus = mailStatus->property("text").toString();
        // A hostile lookalike label must change neither launcher nor status.
        if (!QMetaObject::invokeMethod(
                mailTile, "activated", Qt::DirectConnection,
                Q_ARG(QString, QStringLiteral("Mail;echo bad")))) {
            qCritical() << "MAIL_DOCK_FIXTURE_FAIL: signal not invokable";
            return 1;
        }
        QCoreApplication::processEvents();
        if (mailOverlay->property("opened").toBool()
            || mailStatus->property("text").toString() != initialStatus) {
            qCritical() << "MAIL_DOCK_FIXTURE_FAIL: unknown action accepted";
            return 1;
        }
        if (!QMetaObject::invokeMethod(
                mailTile, "activated", Qt::DirectConnection,
                Q_ARG(QString, QStringLiteral("Mail")))) {
            qCritical() << "MAIL_DOCK_FIXTURE_FAIL: dock activation failed";
            return 1;
        }
        QCoreApplication::processEvents();
        if (mailDockStatusFixture) {
            const QString shown = mailStatus->property("text").toString();
            if (!mailOverlay->property("opened").toBool()
                || !shown.contains(QStringLiteral("Mail could not be launched"))) {
                qCritical() << "MAIL_DOCK_FIXTURE_FAIL: refusal not visible to user";
                return 1;
            }
            qInfo() << "MAIL_DOCK_STATUS_FIXTURE_PASS: refusal visible in launcher footer";
        } else {
            if (mailOverlay->property("opened").toBool()
                || mailStatus->property("text").toString() != initialStatus) {
                qCritical() << "MAIL_DOCK_FIXTURE_FAIL: native launch reported a refusal";
                return 1;
            }
            qInfo() << "SELF_TEST_PASS: Mail dock activated native GIO launch";
            qInfo() << "MAIL_DOCK_LAUNCH_FIXTURE_PASS: dock signal reached GIO service";
        }
        QTimer::singleShot(0, &app, &QCoreApplication::quit);
    }
    const int sizeIndex = args.indexOf(QStringLiteral("--self-test-size"));
    if (sizeIndex >= 0) {
        if (sizeIndex + 1 >= args.size()) {
            qCritical() << "Missing --self-test-size WIDTHxHEIGHT";
            return 2;
        }
        const auto match = QRegularExpression(QStringLiteral("^(\\d+)x(\\d+)$")).match(args.at(sizeIndex + 1));
        if (!match.hasMatch()) {
            qCritical() << "Invalid --self-test-size value";
            return 2;
        }
        const int width = match.captured(1).toInt();
        const int height = match.captured(2).toInt();
        if (width < 720 || height < 480 || width > 3840 || height > 2160) {
            qCritical() << "Self-test size outside supported test range";
            return 2;
        }
        window->resize(width, height);
    }
    const int launcherShotIndex = args.indexOf(
        QStringLiteral("--self-test-launcher-screenshot"));
    if (launcherShotIndex >= 0 &&
        (launcherShotIndex + 1 >= args.size() ||
         !args.at(launcherShotIndex + 1).endsWith(QStringLiteral(".png")) ||
         !args.contains(QStringLiteral("--self-test-screenshot")))) {
        qCritical() << "Missing or invalid --self-test-launcher-screenshot PNG path";
        return 2;
    }
    if (launcherShotIndex >= 0 &&
        launcherShotIndex + 1 < args.size() &&
        args.at(launcherShotIndex + 1) == args.value(
            args.indexOf(QStringLiteral("--self-test-screenshot")) + 1)) {
        qCritical() << "Launcher screenshot must not replace desktop screenshot";
        return 2;
    }
    const bool quickSettingsExpected =
        enableSystemApps && systemLauncher.canLaunch(QStringLiteral("Settings"));
    const int screenshotIndex = args.indexOf(QStringLiteral("--self-test-screenshot"));
    if (screenshotIndex >= 0) {
        if (screenshotIndex + 1 >= args.size()) {
            qCritical() << "Missing screenshot output path";
            return 2;
        }
        const QString screenshotPath = args.at(screenshotIndex + 1);
        const QString launcherScreenshotPath = launcherShotIndex >= 0
            ? args.at(launcherShotIndex + 1) : QString();
        QTimer::singleShot(1000, window,
            [window, screenshotPath, launcherScreenshotPath, approvedMode, landscapeMode,
             framingReviewMode, quickSettingsExpected,
             terminalCandidateMode = !terminalCandidatePath.isEmpty()]() {
            auto *bar = window->findChild<QQuickItem *>(QStringLiteral("canopyTopBar"));
            auto *clock = window->findChild<QQuickItem *>(QStringLiteral("canopyTopBarClock"));
            auto *dock = window->findChild<QQuickItem *>(QStringLiteral("canopyDock"));
            auto *launcher = window->findChild<QQuickItem *>(QStringLiteral("canopyLauncher"));
            auto *preview = window->findChild<QQuickItem *>(QStringLiteral("canopyPreviewWindow"));
            auto *wallpaper = window->findChild<QQuickItem *>(QStringLiteral("canopyWallpaper"));
            if (!bar || !dock || !launcher || !preview || !wallpaper) {
                qCritical() << "SELF_TEST_FAIL: missing required desktop chrome";
                QCoreApplication::exit(1);
                return;
            }
            // Exercise the real QML binding and the one-minute wakeup contract
            // without waiting in CI. Restore the current value before capture.
            if (!clock || !clock->isVisible()
                || !clock->property("refreshScheduled").toBool()) {
                qCritical() << "SELF_TEST_FAIL: local date/time clock absent or inactive";
                QCoreApplication::exit(1);
                return;
            }
            const QVariant originalTime = clock->property("currentTime");
            const QString originalText = clock->property("text").toString();
            const QDateTime controlledMoment(QDate(2037, 4, 5), QTime(9, 41));
            const bool injected = clock->setProperty("currentTime", controlledMoment);
            const QString updatedText = clock->property("text").toString();
            clock->setProperty("currentTime", originalTime);
            if (!injected || originalText.isEmpty() || updatedText == originalText
                || !updatedText.contains(QStringLiteral("9:41"))) {
                qCritical() << "SELF_TEST_FAIL: local clock text is frozen";
                QCoreApplication::exit(1);
                return;
            }
            const QPointF clockOrigin = clock->mapToItem(window->contentItem(), QPointF(0, 0));
            if (clockOrigin.x() < 0 || clockOrigin.y() < 0
                || clockOrigin.x() + clock->width() > window->width()
                || clockOrigin.y() + clock->height() > bar->height() + 1) {
                qCritical() << "SELF_TEST_FAIL: local clock clipped outside top bar";
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: local top bar clock updates and fits";

            // Exercise the registered quick-controls overlay on the real
            // compiled scene, then leave it closed so the captured desktop
            // remains the approved resting composition at every resolution.
            QString quickReason;
            if (!verifyQuickControlsScene(window->contentItem(),
                                          quickSettingsExpected, &quickReason)) {
                qCritical().noquote() << "SELF_TEST_FAIL: quick controls:"
                                      << quickReason;
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: quick controls registered and fail closed";

            // Exercise the integrated QML launcher on the actual compiled
            // scene, then close it before capturing the resting desktop.
            auto *applicationLauncher = findVisualItem(
                window->contentItem(), QStringLiteral("canopyApplicationLauncher"));
            auto *launcherSearch = findVisualItem(
                window->contentItem(), QStringLiteral("canopyLauncherSearch"));
            if (!applicationLauncher || !launcherSearch
                || applicationLauncher->property("catalogCount").toInt() !=
                    (approvedMode ? 8 : 6)
                || !QMetaObject::invokeMethod(applicationLauncher, "openLauncher",
                                               Qt::DirectConnection)
                || !applicationLauncher->isVisible() || !dock->isVisible()) {
                qCritical() << "SELF_TEST_FAIL: original application search failed to open";
                QCoreApplication::exit(1);
                return;
            }
            // Inspect actual QML image components, not just catalog strings.
            QCoreApplication::processEvents();
            const int launcherImageCount = countVisualItems(
                applicationLauncher, QStringLiteral("canopyLauncherIcon"));
            if (launcherImageCount != (approvedMode ? 8 : 6)
                || countReadyLauncherImages(applicationLauncher) != launcherImageCount) {
                qCritical() << "SELF_TEST_FAIL: incomplete launcher image catalogue"
                            << launcherImageCount;
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: actual launcher image component count"
                    << launcherImageCount;
            int centeredLauncherButtons = 0;
            if (!launcherButtonImagesAreCentered(applicationLauncher,
                                                  &centeredLauncherButtons) ||
                centeredLauncherButtons != launcherImageCount) {
                qCritical() << "SELF_TEST_FAIL: launcher icon not centered"
                            << "checked" << centeredLauncherButtons
                            << "images" << launcherImageCount;
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: actual launcher button image geometry centered"
                    << centeredLauncherButtons;
            const bool selectedMatch =
                applicationLauncher->setProperty("searchQuery", QStringLiteral("fIlEs"))
                && applicationLauncher->property("filteredCount").toInt() == 1;
            const bool emptyMatch =
                applicationLauncher->setProperty("searchQuery", QStringLiteral("no-such-canopy-application"))
                && applicationLauncher->property("filteredCount").toInt() == 0;
            const bool restoredMatch =
                applicationLauncher->setProperty("searchQuery", QString())
                && applicationLauncher->property("filteredCount").toInt() ==
                    (approvedMode ? 8 : 6);
            const bool closed = QMetaObject::invokeMethod(
                applicationLauncher, "closeLauncher", Qt::DirectConnection)
                && !applicationLauncher->isVisible() && dock->isVisible();
            if (!selectedMatch || !emptyMatch || !restoredMatch || !closed) {
                qCritical() << "SELF_TEST_FAIL: launcher search or dismissal inconsistent";
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: actual Qt launcher opens, searches and closes";
            if (framingReviewMode)
                qInfo() << "SELF_TEST_PASS: launcher-only Qt frame review enabled; dock frozen";

            const QPointF barOrigin = bar->mapToItem(window->contentItem(), QPointF(0, 0));
            const QPointF dockOrigin = dock->mapToItem(window->contentItem(), QPointF(0, 0));
            const bool barFits = qAbs(barOrigin.x()) <= 2 && qAbs(barOrigin.y()) <= 2
                && qAbs(bar->width() - window->width()) <= 2 && bar->height() >= 30;
            const bool dockFits = dockOrigin.x() >= 0 && dockOrigin.y() >= bar->height()
                && dockOrigin.x() + dock->width() <= window->width() + 1
                && dockOrigin.y() + dock->height() <= window->height() + 1
                && qAbs(dockOrigin.x() + dock->width() / 2 - window->width() / 2) <= 2;
            if (!launcher->property("imageReady").toBool()) {
                qCritical() << "SELF_TEST_FAIL: original Canopy launcher icon did not load";
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: original Canopy penguin launcher loaded";
            const QPointF launcherOrigin = launcher->mapToItem(window->contentItem(), QPointF(0, 0));
            const bool launcherFits = launcher->width() >= 24 && launcher->height() >= 28
                && launcherOrigin.x() >= 0 && launcherOrigin.y() >= 0
                && launcherOrigin.x() + launcher->width() <= window->width()
                && launcherOrigin.y() + launcher->height() <= bar->height() + 1;
            if (!barFits || !dockFits || !launcherFits) {
                qCritical() << "SELF_TEST_FAIL: desktop chrome geometry invalid"
                            << "window" << window->size() << "bar" << barOrigin << bar->size()
                            << "dock" << dockOrigin << dock->size()
                            << "launcher" << launcherOrigin << launcher->size();
                QCoreApplication::exit(1);
                return;
            }
            const QPointF previewOrigin = preview->mapToItem(window->contentItem(), QPointF(0, 0));
            const bool previewFits = previewOrigin.x() >= 0
                && previewOrigin.y() >= bar->height() - 1
                && previewOrigin.x() + preview->width() <= window->width() + 1
                && previewOrigin.y() + preview->height() <= dockOrigin.y() - 12
                && preview->width() >= 480 && preview->height() >= 250;
            if (!previewFits) {
                qCritical() << "SELF_TEST_FAIL: preview overlaps desktop chrome or is too small"
                            << "window" << window->size() << "preview" << previewOrigin
                            << preview->size() << "dock" << dockOrigin << dock->size();
                QCoreApplication::exit(1);
                return;
            }
            const int dockTileCount = countVisualItems(dock, QStringLiteral("canopyDockTile"));
            if (!wallpaper->property("imageReady").toBool()) {
                if (landscapeMode)
                    qCritical() << "SELF_TEST_FAIL: validated landscape wallpaper did not decode";
                else
                    qCritical() << "SELF_TEST_FAIL: Blue Current wallpaper image did not load"
                                << "check Qt SVG plugin and embedded artwork";
                QCoreApplication::exit(1);
                return;
            }
            if (landscapeMode)
                qInfo() << "SELF_TEST_PASS: validated custom landscape wallpaper loaded";
            else
                qInfo() << "SELF_TEST_PASS: original SVG wallpaper image loaded";
            const QPointF wallpaperOrigin = wallpaper->mapToItem(window->contentItem(), QPointF(0, 0));
            const bool wallpaperFits = qAbs(wallpaperOrigin.x()) <= 1
                && qAbs(wallpaperOrigin.y()) <= 1
                && qAbs(wallpaper->width() - window->width()) <= 1
                && qAbs(wallpaper->height() - window->height()) <= 1;
            const int iconReadyCount = countReadyDockTiles(dock);
            if (iconReadyCount != (approvedMode ? 8 : 6)) {
                qCritical() << "SELF_TEST_FAIL: original dock artwork failed to load"
                            << "ready icons" << iconReadyCount;
                QCoreApplication::exit(1);
                return;
            }
            if (approvedMode && terminalCandidateMode)
                qInfo() << "SELF_TEST_PASS: seven original dock PNGs plus one Terminal candidate loaded";
            else if (approvedMode)
                qInfo() << "SELF_TEST_PASS: all eight exact approved dock PNGs loaded";
            else
                qInfo() << "SELF_TEST_PASS: all six SVG dock candidates loaded (legacy demo only)";
            {
                // Also exercise this geometry check in CI's six-icon legacy
                // scene so the layout cannot regress when approved PNGs are
                // unavailable on the runner. Full eight-icon QA runs locally.
                // A successful icon decoder doesn't prove the dock looks aligned.
                // Test all eight ACTUAL QML image rectangles in the running scene.
                // Each 54px art slot must be centred on its 58x70px button,
                // and its button must be centered vertically inside the dock.
                const QStringList names = approvedMode ? QStringList{
                    QStringLiteral("Browser"), QStringLiteral("Mail"),
                    QStringLiteral("Files"), QStringLiteral("Calendar"),
                    QStringLiteral("Photos"), QStringLiteral("Music"),
                    QStringLiteral("Terminal"), QStringLiteral("Settings")
                } : QStringList{
                    QStringLiteral("Files"), QStringLiteral("Browser"),
                    QStringLiteral("Settings"), QStringLiteral("Photos"),
                    QStringLiteral("Terminal"), QStringLiteral("Trash")
                };
                qreal previousRight = -1;
                for (const QString &name : names) {
                    auto *button = findDockTile(dock, name);
                    auto *art = button ? findVisualItem(button, QStringLiteral("canopyDockIcon"))
                                       : nullptr;
                    if (!button || !art) {
                        qCritical() << "SELF_TEST_FAIL: dock centering missing control" << name;
                        QCoreApplication::exit(1);
                        return;
                    }
                    const QPointF iconStart = art->mapToItem(dock, QPointF(0, 0));
                    const QPointF tileStart = button->mapToItem(dock, QPointF(0, 0));
                    const qreal iconMidX = iconStart.x() + art->width() / 2;
                    const qreal iconMidY = iconStart.y() + art->height() / 2;
                    const qreal buttonMidX = tileStart.x() + button->width() / 2;
                    const qreal buttonMidY = tileStart.y() + button->height() / 2;
                    if (qAbs(iconMidX - buttonMidX) > 0.75 ||
                        qAbs(iconMidY - buttonMidY) > 0.75 ||
                        qAbs(iconMidY - dock->height() / 2) > 1.0 ||
                        iconStart.y() < 7 || iconStart.y() + art->height()
                             > dock->height() - 7 ||
                        tileStart.x() < previousRight ||
                        art->width() < 50 || art->width() > 56 ||
                        art->height() != art->width()) {
                        qCritical() << "SELF_TEST_FAIL: dock icon optical alignment"
                                    << name << "image" << iconStart << art->size()
                                    << "tile" << tileStart << button->size()
                                    << "dock" << dock->size();
                        QCoreApplication::exit(1);
                        return;
                    }
                    previousRight = tileStart.x() + button->width();
                }
                qInfo() << "SELF_TEST_PASS: dock icons horizontally/vertically centred"
                        << "count" << names.size()
                        << "with equal 54px art slots and 7px minimum dock insets";
            }
            if (!wallpaperFits || dockTileCount != (approvedMode ? 8 : 6)) {
                qCritical() << "SELF_TEST_FAIL: wallpaper bounds or dock icon count invalid"
                            << "wallpaper" << wallpaperOrigin << wallpaper->size()
                            << "icon count" << dockTileCount;
                QCoreApplication::exit(1);
                return;
            }
            const int folderCount = countVisualItems(preview, QStringLiteral("canopyFolderTile"));
            const int searchCount = countVisualItems(preview, QStringLiteral("canopyPreviewSearch"));
            if (folderCount != 8 || searchCount != 1) {
                qCritical() << "SELF_TEST_FAIL: sample Files preview content incomplete"
                            << "sample folders" << folderCount << "search inputs" << searchCount;
                QCoreApplication::exit(1);
                return;
            }
            auto *folderScroller = findVisualItem(
                preview, QStringLiteral("canopyFolderScroller"));
            // An always-visible scrollbar previously masked clipped folder
            // rows at 760x500. Require two fully visible rows on compact
            // captures and a four-column cap at larger resolutions.
            auto *folderFlow = findVisualItem(
                preview, QStringLiteral("canopyFolderFlow"));
            const bool compactGrid = window->width() <= 800;
            const bool folderGridFits = folderScroller &&
                folderScroller->property("contentHeight").toDouble()
                    <= folderScroller->height() + 3;
            const bool fourColumnGrid = folderFlow &&
                folderFlow->width() <= 462.5 &&
                folderFlow->width() >= 449.5;
            if (!folderScroller || !folderScroller->clip() || !fourColumnGrid
                || (compactGrid && !folderGridFits)) {
                qCritical() << "SELF_TEST_FAIL: Files folder grid clipped or unbalanced"
                            << "compact" << compactGrid
                            << "viewport" << (folderScroller ? folderScroller->height() : 0)
                            << "content" << (folderScroller ?
                                folderScroller->property("contentHeight").toDouble() : 0)
                            << "gridWidth" << (folderFlow ? folderFlow->width() : 0);
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: compact folder grid fits and four-column cap verified";
            const int folderArtworkReady = countReadyFolderTiles(preview);
            if (folderArtworkReady != 8) {
                qCritical() << "SELF_TEST_FAIL: folder artwork did not load"
                            << "ready sample folders" << folderArtworkReady;
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: all eight original sample folder images loaded";
            qInfo() << "SELF_TEST_PASS: eight demo folders and one search control present";
            if (approvedMode && landscapeMode)
                qInfo() << "SELF_TEST_PASS: eight SHA-locked icon PNGs and separate landscape wallpaper present";
            else if (approvedMode)
                qInfo() << "SELF_TEST_PASS: verified user-supplied blue wave and eight selected PNG icons present";
            else
                qInfo() << "SELF_TEST_PASS: original wallpaper and six dock icon candidates present";
            qInfo() << "SELF_TEST_PASS: preview window fits above dock" << previewOrigin
                    << preview->size();
            qInfo() << "SELF_TEST_PASS: desktop chrome geometry" << window->size();
            // Exercise the actual QML Button clicked signal, not only source strings.
            // Toggle twice so the screenshot remains the original visible scene.
            auto *filesTile = findDockTile(dock, QStringLiteral("Files"));
            if (!filesTile || !preview->isVisible() ||
                !filesTile->property("previewActive").toBool() ||
                !QMetaObject::invokeMethod(filesTile, "clicked", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files dock click setup invalid";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (preview->isVisible() || filesTile->property("previewActive").toBool()) {
                qCritical() << "SELF_TEST_FAIL: Files dock did not hide preview";
                QCoreApplication::exit(1);
                return;
            }
            if (!QMetaObject::invokeMethod(filesTile, "clicked", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files dock second click failed";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (!preview->isVisible() || !filesTile->property("previewActive").toBool()) {
                qCritical() << "SELF_TEST_FAIL: Files dock did not restore preview";
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: Files dock hide/restore and activity indicator";
            auto *closeControl = findVisualItem(preview, QStringLiteral("canopyPreviewClose"));
            if (!closeControl ||
                !QMetaObject::invokeMethod(closeControl, "clicked", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files close control missing or inactive";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (preview->isVisible() || filesTile->property("previewActive").toBool()) {
                qCritical() << "SELF_TEST_FAIL: Files close control did not hide preview";
                QCoreApplication::exit(1);
                return;
            }
            if (!QMetaObject::invokeMethod(filesTile, "clicked", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files dock could not reopen closed preview";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (!preview->isVisible() || !filesTile->property("previewActive").toBool()) {
                qCritical() << "SELF_TEST_FAIL: Files preview failed to reopen after close";
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: Files close control and dock reopen";
            // Trigger the QML shortcut signals directly to verify bindings;
            // this does not claim OS-level keyboard dispatch or global hooks.
            auto *closeShortcut = window->findChild<QObject *>(
                QStringLiteral("canopyFilesCloseShortcut"));
            auto *openShortcut = window->findChild<QObject *>(
                QStringLiteral("canopyFilesOpenShortcut"));
            if (!closeShortcut || !openShortcut ||
                !closeShortcut->property("enabled").toBool() ||
                !QMetaObject::invokeMethod(closeShortcut, "activated", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files keyboard close shortcut unavailable";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (preview->isVisible() || !openShortcut->property("enabled").toBool() ||
                !QMetaObject::invokeMethod(openShortcut, "activated", Qt::DirectConnection)) {
                qCritical() << "SELF_TEST_FAIL: Files keyboard shortcut close/open failed";
                QCoreApplication::exit(1);
                return;
            }
            QCoreApplication::processEvents();
            if (!preview->isVisible() || !closeShortcut->property("enabled").toBool()) {
                qCritical() << "SELF_TEST_FAIL: Files keyboard shortcut did not reopen preview";
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: Files keyboard close and reopen bindings";
            const QImage frame = window->grabWindow();
            if (frame.isNull() || frame.width() < 720 || frame.height() < 480) {
                qCritical() << "SELF_TEST_FAIL: invalid screenshot dimensions";
                QCoreApplication::exit(1);
                return;
            }
            QSet<QRgb> sampledColors;
            for (int y = 0; y < frame.height(); y += qMax(1, frame.height() / 12)) {
                for (int x = 0; x < frame.width(); x += qMax(1, frame.width() / 12)) {
                    sampledColors.insert(frame.pixel(x, y));
                }
            }
            // Prove the *visible wallpaper* varies, without trusting just one
            // chosen sky/foreground pair. Scenic photos may give two similar
            // colors at a narrow display's left edge; both outer strips remain
            // unobscured by the central demo Files window at supported sizes.
            const int edgeX = qMax(2, frame.width() / 100);
            const int edgeXs[] = { edgeX, frame.width() - edgeX - 1 };
            QVector<QRgb> wallpaperSamples;
            for (int x : edgeXs) {
                for (int y = qMax(50, frame.height() / 8);
                     y < frame.height() - 10;
                     y += qMax(1, frame.height() / 10)) {
                    wallpaperSamples.append(frame.pixel(x, y));
                }
            }
            int maxArtworkDifference = 0;
            for (int i = 0; i < wallpaperSamples.size(); ++i) {
                for (int j = 0; j < i; ++j) {
                    const QRgb a = wallpaperSamples.at(i);
                    const QRgb b = wallpaperSamples.at(j);
                    maxArtworkDifference = qMax(maxArtworkDifference,
                        qAbs(qRed(a) - qRed(b)) +
                        qAbs(qGreen(a) - qGreen(b)) +
                        qAbs(qBlue(a) - qBlue(b)));
                }
            }
            if (maxArtworkDifference < 55) {
                qCritical() << "SELF_TEST_FAIL: wallpaper regions unexpectedly uniform"
                            << "maximum color distance" << maxArtworkDifference;
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: wallpaper regions visually distinct";
            if (sampledColors.size() < 8) {
                qCritical() << "SELF_TEST_FAIL: screenshot appears blank or uniform";
                QCoreApplication::exit(1);
                return;
            }
            if (!frame.save(screenshotPath, "PNG")) {
                qCritical() << "SELF_TEST_FAIL: could not capture window" << screenshotPath;
                QCoreApplication::exit(1);
                return;
            }
            qInfo() << "SELF_TEST_PASS: nonuniform window screenshot captured" << frame.size()
                    << "sampled colors" << sampledColors.size();
            if (!launcherScreenshotPath.isEmpty()) {
                if (!QMetaObject::invokeMethod(applicationLauncher, "openLauncher",
                                               Qt::DirectConnection)) {
                    qCritical() << "SELF_TEST_FAIL: could not open launcher for capture";
                    QCoreApplication::exit(1);
                    return;
                }
                // Neutralize Xvfb's default pointer hover so transient tooltips
                // cannot obscure the owner's actual-open visual evidence.
                QCursor::setPos(window->mapToGlobal(QPoint(
                    8, window->height() - 8)));
                // QQuickWindow::grabWindow() returns PHYSICAL pixels.
                // Never compare those dimensions to logical QQuickWindow
                // geometry: at 150% scale, a 1200x750 window is 1800x1125.
                // Require both actual Qt captures to share the exact same
                // pixel dimensions instead; this catches clipped/stale frames
                // while allowing legitimate high-DPI device pixel ratios.
                const QSize desktopPhysicalPixels = frame.size();
                QTimer::singleShot(250, window,
                    [window, applicationLauncher, launcherScreenshotPath,
                     desktopPhysicalPixels]() {
                        const QImage launcherFrame = window->grabWindow();
                        if (!applicationLauncher->isVisible() ||
                            launcherFrame.isNull() ||
                            launcherFrame.size() != desktopPhysicalPixels ||
                            !launcherFrame.save(launcherScreenshotPath, "PNG")) {
                            qCritical() << "SELF_TEST_FAIL: actual launcher screenshot unavailable";
                            QCoreApplication::exit(1);
                            return;
                        }
                        qInfo() << "SELF_TEST_PASS: actual launcher overlay screenshot captured"
                                << launcherFrame.size();
                        QCoreApplication::quit();
                    });
                return;
            }
            QCoreApplication::quit();
        });
    }
    return app.exec();
}

#include "main.moc"
