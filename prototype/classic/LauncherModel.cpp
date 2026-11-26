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
