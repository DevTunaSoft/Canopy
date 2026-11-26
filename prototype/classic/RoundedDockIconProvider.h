#pragma once

#include <QByteArray>
#include <QHash>
#include <QImage>
#include <QQuickImageProvider>
#include <QString>

// All eight verified original PNGs stay untouched on disk. Once after source
// verification, this provider renders padded, antialiased, rounded previews
// into a small fixed cache; no shader, per-frame crop, or polling loop.
class RoundedDockIconProvider final : public QQuickImageProvider {
public:
    explicit RoundedDockIconProvider(const QString &approvedRoot,
                                     const QString &terminalCandidatePath,
                                     bool framingReviewMode, QString *error,
                                     bool balancedDockFitMode = false,
                                     bool opticalBalanceReviewMode = false,
                                     bool cleanSourceEdgesReviewMode = false,
                                     bool fiveOnlyCenterReviewMode = false,
                                     const QString &productionPackRoot = QString(),
                                     QHash<QString, QByteArray> *verifiedBytes = nullptr);

    bool isValid() const { return m_images.size() == 8; }
    bool allCornersClipped() const;
    bool productionPackVerified() const { return m_productionPackValid; }
    bool exportFiveProductionPack(const QString &outputRoot,
                                  const QString &approvedRoot,
                                  QString *error) const;
    QImage requestImage(const QString &id, QSize *size,
                        const QSize &requestedSize) override;

private:
    QHash<QString, QImage> m_images;
    QHash<QString, QString> m_productionMasterPaths;
    QString m_productionPackRoot;
    bool m_productionPackValid = false;
};

// Strictly opt-in preview provider for the eight owner-supplied Tux PNGs.
// It returns the decoded bytes of the exact verified files: no painter,
// crop, recolor, regeneration or compositing is performed here. Startup
// verification in main.cpp fails closed before this object is constructed;
// this provider re-hashes each file as a second independent gate.
class OwnerIconsPreviewProvider final : public QQuickImageProvider {
public:
    explicit OwnerIconsPreviewProvider(const QString &previewRoot,
                                       QString *error);

    bool isValid() const { return m_images.size() == 8; }
    QImage requestImage(const QString &id, QSize *size,
                        const QSize &requestedSize) override;

private:
    QHash<QString, QImage> m_images;
};
