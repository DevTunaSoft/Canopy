#include "LauncherModel.h"

#include <QByteArray>
#include <QChar>
#include <QDebug>
#include <QFile>
#include <QSet>
#include <QStringDecoder>
#include <QVariantMap>

// Mirrors canopy_features/apps/launch_argv.DESKTOP_ID:
//   [A-Za-z0-9][A-Za-z0-9._-]*\.desktop
// The id is display metadata only; it is never turned into a path or a launch.
bool LauncherCatalogModel::validAppId(const QString &appId)
{
    static const QString suffix = QStringLiteral(".desktop");
    if (appId.size() <= suffix.size() || !appId.endsWith(suffix))
        return false;
    const int stemLength = appId.size() - suffix.size();
    const QChar first = appId.at(0);
    const auto alnum = [](const QChar &c) {
        return (c >= QLatin1Char('a') && c <= QLatin1Char('z'))
            || (c >= QLatin1Char('A') && c <= QLatin1Char('Z'))
            || (c >= QLatin1Char('0') && c <= QLatin1Char('9'));
    };
    if (!alnum(first))
        return false;
    for (int i = 1; i < stemLength; ++i) {
        const QChar c = appId.at(i);
        if (!alnum(c) && c != QLatin1Char('.') && c != QLatin1Char('_')
            && c != QLatin1Char('-'))
            return false;
    }
    return true;
}

// Mirrors the pure-Python title guard: reject every control/format/surrogate/
// private-use/unassigned/line/paragraph scalar, keep ordinary spacing.
bool LauncherCatalogModel::validTitle(const QString &title)
{
    if (title.isEmpty() || title.size() > MaxTitleChars)
        return false;
    for (int i = 0; i < title.size(); ++i) {
        const QChar c = title.at(i);
        const ushort code = c.unicode();
        if (c.isSurrogate() || code < 0x20 || code == 0x7f)
            return false;
        switch (c.category()) {
        case QChar::Other_Control:
        case QChar::Other_Format:
        case QChar::Other_Surrogate:
        case QChar::Other_PrivateUse:
        case QChar::Other_NotAssigned:
        case QChar::Separator_Line:
        case QChar::Separator_Paragraph:
            return false;
        default:
            break;
        }
    }
    return true;
}

QStringList LauncherCatalogModel::titles() const
{
    QStringList result;
    result.reserve(m_rows.size());
    for (const LauncherCatalogRow &row : m_rows)
        result.append(row.title);
    return result;
}

QStringList LauncherCatalogModel::appIds() const
{
    QStringList result;
    result.reserve(m_rows.size());
    for (const LauncherCatalogRow &row : m_rows)
        result.append(row.appId);
    return result;
}

QVariantList LauncherCatalogModel::applications() const
{
    QVariantList result;
    result.reserve(m_rows.size());
    for (const LauncherCatalogRow &row : m_rows) {
        QVariantMap entry;
        entry.insert(QStringLiteral("title"), row.title);
        result.append(entry);
    }
    return result;
}

LauncherModel::View LauncherCatalogModel::browse() const
{
    return LauncherModel::browse(titles());
}

LauncherModel::View LauncherCatalogModel::filter(const QString &query,
                                                 int limit) const
{
    return LauncherModel::filter(query, titles(), limit);
}

bool LauncherCatalogModel::applyRows(const QVector<LauncherCatalogRow> &rows)
{
    if (rows.isEmpty() || rows.size() > MaxRows)
        return false;
    QSet<QString> seenIds;
    for (const LauncherCatalogRow &row : rows) {
        if (!validAppId(row.appId) || !validTitle(row.title))
            return false;
        if (seenIds.contains(row.appId))
            return false;
        seenIds.insert(row.appId);
    }
    // Commit only after every row has passed; a rejected snapshot never
    // replaces a previously accepted one.
    m_rows = rows;
    m_rawCount = rows.size();
    m_duplicateIdCount = 0;
    m_active = true;
    return true;
}

bool LauncherCatalogModel::loadFromText(const QString &text)
{
    if (text.isEmpty())
        return false;
    QVector<LauncherCatalogRow> rows;
    QSet<QString> seenIds;
    int rawCount = 0;
    int duplicateIds = 0;
    const QStringList lines = text.split(QLatin1Char('\n'));
    for (int lineIndex = 0; lineIndex < lines.size(); ++lineIndex) {
        QString line = lines.at(lineIndex);
        // A single trailing CR is the CRLF convention, matching the
        // pure-Python parser; any other CR is caught by validTitle.
        if (line.endsWith(QLatin1Char('\r')))
            line.chop(1);
        // One terminating LF is normal; interior blank lines are not.
        if (line.isEmpty() && lineIndex == lines.size() - 1)
            continue;
        if (line.isEmpty())
            return false;
        const int tab = line.indexOf(QLatin1Char('\t'));
        if (tab <= 0 || tab != line.lastIndexOf(QLatin1Char('\t'))
            || tab + 1 >= line.size())
            return false;
        const QString appId = line.left(tab);
        const QString title = line.mid(tab + 1);
        if (!validAppId(appId) || !validTitle(title))
            return false;
        if (++rawCount > MaxRows)
            return false;
        if (seenIds.contains(appId)) {
            ++duplicateIds;
            continue;  // first occurrence wins, as in the Python contract
        }
        seenIds.insert(appId);
        rows.append(LauncherCatalogRow{appId, title});
    }
    if (rows.isEmpty())
        return false;
    // Commit only after the whole snapshot is proven clean.
    m_rows = rows;
    m_rawCount = rawCount;
    m_duplicateIdCount = duplicateIds;
    m_active = true;
    return true;
}

bool LauncherCatalogModel::loadFromFile(const QString &path)
{
    // Explicit-path, read-only access. No XDG walk, glob, process, socket or
    // write: the trusted host names exactly one already-produced snapshot.
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly))
        return false;
    const qint64 size = file.size();
    if (size <= 0 || size > MaxSnapshotBytes)
        return false;
    const QByteArray bytes = file.read(MaxSnapshotBytes + 1);
    if (bytes.size() != size || bytes.isEmpty() || bytes.contains('\0'))
        return false;
    QStringDecoder decoder(QStringConverter::Utf8,
                           QStringConverter::Flag::Stateless);
    const QString text = decoder.decode(bytes);
    if (decoder.hasError() || text.isEmpty())
        return false;
    return loadFromText(text);
}

// Compiled mirror of the merged enumeration-source contract. This function
// never resolves, stats or opens a path: a bad descriptor is refused before
// any snapshot is returned, and ordering is fixed by role then path.
QString LauncherEnumerationSources::roleToken(Role role)
{
    switch (role) {
    case Role::Explicit:     return QStringLiteral("explicit");
    case Role::XdgDataDirs:  return QStringLiteral("xdg_data_dirs");
    case Role::XdgDataHome:  return QStringLiteral("xdg_data_home");
    }
    return QString();
}

bool LauncherEnumerationSources::validPath(const QString &path)
{
    if (path.isEmpty() || path.size() > MaxPathChars)
        return false;
    const bool posix = path.startsWith(QLatin1Char('/'));
    const QChar drive = path.at(0);
    const bool windows = path.size() >= 3
        && ((drive >= QLatin1Char('a') && drive <= QLatin1Char('z'))
            || (drive >= QLatin1Char('A') && drive <= QLatin1Char('Z')))
        && path.at(1) == QLatin1Char(':')
        && (path.at(2) == QLatin1Char('/') || path.at(2) == QLatin1Char('\\'));
    if (!posix && !windows)
        return false;

    QString component;
    for (int i = 0; i <= path.size(); ++i) {
        const bool separator = i == path.size()
            || path.at(i) == QLatin1Char('/') || path.at(i) == QLatin1Char('\\');
        if (!separator) {
            const QChar c = path.at(i);
            const ushort code = c.unicode();
            if (c.isSurrogate() || code < 0x20 || code == 0x7f)
                return false;
            switch (c.category()) {
            case QChar::Other_Control:
            case QChar::Other_Format:
            case QChar::Other_Surrogate:
            case QChar::Other_PrivateUse:
            case QChar::Other_NotAssigned:
            case QChar::Separator_Line:
            case QChar::Separator_Paragraph:
                return false;
            default:
                break;
            }
            component.append(c);
            continue;
        }
        if (component == QLatin1String(".."))
            return false;
        component.clear();
    }
    return true;
}

bool LauncherEnumerationSources::describe(const QVector<Source> &input,
                                          Snapshot *out)
{
    if (!out || input.size() > MaxSources)
        return false;
    Snapshot snapshot;
    QSet<QString> seen;
    int total = 0;
    for (const Source &source : input) {
        const QString token = roleToken(source.role);
        if (token.isEmpty() || source.maxEntries < 1
            || source.maxEntries > MaxEntriesPerSource
            || !validPath(source.path))
            return false;
        const QString key = token + QLatin1Char('\x1f') + source.path;
        if (seen.contains(key))
            return false;
        seen.insert(key);
        total += source.maxEntries;
        if (total > MaxTotalEntries)
            return false;
        snapshot.sources.append(source);
    }
    std::stable_sort(snapshot.sources.begin(), snapshot.sources.end(),
                     [](const Source &a, const Source &b) {
                         const int role = roleToken(a.role)
                                              .compare(roleToken(b.role));
                         return role != 0 ? role < 0 : a.path < b.path;
                     });
    snapshot.totalEntries = total;
    *out = snapshot;
    return true;
}

bool LauncherCatalogRefresh::validSourceIdentity(const QString &source)
{
    if (source.isEmpty() || source.size() > MaxSourceChars)
        return false;
    for (const QChar c : source) {
        const ushort code = c.unicode();
        const bool legal = (code >= 'a' && code <= 'z')
            || (code >= '0' && code <= '9') || code == '_' || code == '.'
            || code == ':' || code == '-';
        if (!legal)
            return false;
    }
    return true;
}

QString LauncherCatalogRefresh::outcomeToken(Outcome outcome)
{
    switch (outcome) {
    case Outcome::Rejected:  return QStringLiteral("event_rejected");
    case Outcome::Refused:   return QStringLiteral("snapshot_refused");
    case Outcome::Frozen:    return QStringLiteral("refresh_limit");
    case Outcome::Unchanged: return QStringLiteral("unchanged");
    case Outcome::Refreshed: return QStringLiteral("refreshed");
    }
    return QStringLiteral("event_rejected");
}

bool LauncherCatalogRefresh::wireIds(const QString &text, QSet<QString> *ids)
{
    if (!ids || text.isEmpty()
        || text.toUtf8().size() > LauncherCatalogModel::MaxSnapshotBytes)
        return false;
    const QStringList lines = text.split(QLatin1Char('\n'));
    int rows = 0;
    for (int i = 0; i < lines.size(); ++i) {
        QString line = lines.at(i);
        if (line.endsWith(QLatin1Char('\r')))
            line.chop(1);
        if (line.isEmpty() && i == lines.size() - 1)
            continue;
        const int tab = line.indexOf(QLatin1Char('\t'));
        if (tab <= 0 || tab != line.lastIndexOf(QLatin1Char('\t'))
            || tab + 1 >= line.size())
            return false;
        const QString appId = line.left(tab);
        if (!LauncherCatalogModel::validAppId(appId)
            || !LauncherCatalogModel::validTitle(line.mid(tab + 1))
            || ids->contains(appId) || ++rows > LauncherCatalogModel::MaxRows)
            return false;
        ids->insert(appId);
    }
    return rows > 0;
}

LauncherCatalogRefresh::LauncherCatalogRefresh(LauncherCatalogModel &model,
                                               QString trustedSource,
                                               Producer producer)
    : m_model(model),
      m_trustedSource(std::move(trustedSource)),
      m_producer(std::move(producer))
{
    // An invalid source identity or missing producer fails the gate closed at
    // construction; no event can ever open it.
    if (!validSourceIdentity(m_trustedSource) || !m_producer)
        m_closed = true;
    // An already-displayed opt-in snapshot is the baseline: its installed
    // ids are authoritative until a trusted event replaces the wire.
    for (const QString &appId : model.appIds())
        m_ids.insert(appId);
}

bool LauncherCatalogRefresh::applyHostEvent(const QString &topic,
                                            const QVariantMap &payload)
{
    Report report;
    const QVariant source = payload.value(QStringLiteral("source"));
    const QVariant sequence = payload.value(QStringLiteral("sequence"));
    const int sequenceValue = sequence.metaType() == QMetaType(QMetaType::Int)
                                  ? sequence.toInt() : 0;

    const auto reject = [this, &report]() {
        ++m_rejections;
        m_lastReport = report;
        return false;
    };
    if (m_closed || topic != QStringLiteral("app.catalog.changed")
        || source.metaType() != QMetaType(QMetaType::QString)
        || source.toString() != m_trustedSource
        || sequenceValue < 1 || sequenceValue <= m_lastSequence)
        return reject();

    if (m_eventsApplied >= MaxRefreshEvents) {
        report.outcome = Outcome::Frozen;
        report.sequence = sequenceValue;
        report.producerCalls = 0;
        report.snapshotBytes = static_cast<int>(m_model.titles().size());
        ++m_rejections;
        m_lastReport = report;
        return false;
    }

    ++m_producerCalls;
    report.sequence = sequenceValue;
    report.producerCalls = 1;
    QString wire;
    QSet<QString> ids;
    bool produced = false;
    try {
        produced = m_producer(&wire);
    } catch (...) {
        produced = false;
    }
    if (!produced || !wireIds(wire, &ids) || !m_model.loadFromText(wire)) {
        report.outcome = Outcome::Refused;
        report.snapshotBytes = 0;
        ++m_eventsApplied;
        ++m_rejections;
        m_lastReport = report;
        return false;
    }

    report.installedCount = (ids - m_ids).size();
    report.removedCount = (m_ids - ids).size();
    report.snapshotBytes = static_cast<int>(wire.toUtf8().size());
    report.outcome = (report.installedCount || report.removedCount)
                         ? Outcome::Refreshed : Outcome::Unchanged;
    m_ids = ids;
    m_lastSequence = sequenceValue;
    ++m_eventsApplied;
    m_lastReport = report;
    return true;
}

static bool catalogCheck(bool ok, const char *name)
{
    qInfo().noquote() << (ok ? "CATALOG_PASS " : "CATALOG_FAIL ") << name;
    return ok;
}

bool LauncherCatalogModel::selfTest()
{
    LauncherCatalogModel fresh;
    bool ok = true;
    ok &= catalogCheck(!fresh.active() && fresh.rowCount() == 0,
                       "default inactive fail closed");
    ok &= catalogCheck(fresh.loadFromText(
                           QStringLiteral("org.example.Files.desktop\tFiles\n"
                                          "org.example.Browser.desktop\tBrowser\n"
                                          "org.example.Terminal.desktop\tTerminal\n")),
                       "bounded text ingest");
    ok &= catalogCheck(fresh.active() && fresh.rowCount() == 3
                       && fresh.titles().at(0) == QStringLiteral("Files")
                       && fresh.titles().at(2) == QStringLiteral("Terminal"),
                       "snapshot order");
    ok &= catalogCheck(fresh.applications().size() == 3
                       && fresh.applications().at(1).toMap()
                              .value(QStringLiteral("title")).toString()
                              == QStringLiteral("Browser"),
                       "QML bridge shape");
    ok &= catalogCheck(fresh.filter(QStringLiteral("fIlEs")).count() == 1
                       && fresh.browse().count() == 3,
                       "host-side filter parity");
    LauncherCatalogModel hostile;
    ok &= catalogCheck(!hostile.loadFromText(
                           QStringLiteral("org.example.One.desktop\tOne\nbad id\tTwo\n")),
                       "invalid id fails closed");
    ok &= catalogCheck(!hostile.loadFromText(
                           QStringLiteral("../evil.desktop\tFiles\n")),
                       "path-like id fails closed");
    ok &= catalogCheck(!hostile.loadFromText(
                           QStringLiteral("org.example.One.desktop\tFi\nles\n")),
                       "control title fails closed");
    ok &= catalogCheck(!hostile.loadFromText(
                           QStringLiteral("org.example.One.desktop\t")),
                       "empty title fails closed");
    ok &= catalogCheck(!hostile.active() && hostile.rowCount() == 0,
                       "rejected snapshot leaves model empty");
    // A valid load after hostile input proves the guards did not poison state.
    ok &= catalogCheck(hostile.loadFromText(
                           QStringLiteral("org.example.One.desktop\tFiles\n"))
                       && hostile.rowCount() == 1,
                       "recovery after refusal");
    ok &= catalogCheck(!hostile.loadFromFile(
                           QStringLiteral("C:/canopy/no-such-launcher-catalog.tsv")),
                       "missing file fails closed");
    qInfo().noquote() << (ok ? "CATALOG_ALL_PASS" : "CATALOG_ALL_FAIL");
    return ok;
}
