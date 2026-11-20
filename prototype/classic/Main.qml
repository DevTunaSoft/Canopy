import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1200
    height: 750
    minimumWidth: 720
    minimumHeight: 480
    visible: true
    title: "Canopy Classic — Technology Spike"
    color: "#09111d"

    Theme { id: canopyTheme }
    readonly property bool compactLayout: width < 900

    // Lightweight wallpaper composition: gradients and rectangles only.
    // No shader effects, animation loops, timers or additional processes.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: canopyTheme.backgroundTop }
            GradientStop { position: 1; color: canopyTheme.backgroundBottom }
        }
    }
    Rectangle {
        width: root.width * 1.04
        height: root.height * 0.78
        x: root.width * 0.22
        y: root.height * 0.25
        rotation: -27
        radius: height * 0.45
        opacity: 0.50
        gradient: Gradient {
            GradientStop { position: 0; color: "#365a7a" }
            GradientStop { position: 0.45; color: "#253c59" }
            GradientStop { position: 1; color: "#0c1727" }
        }
    }
    Rectangle {
        width: root.width * 0.83
        height: root.height * 0.44
        x: root.width * 0.40
        y: root.height * 0.65
        rotation: -16
        radius: height * 0.45
        opacity: 0.46
        gradient: Gradient {
            GradientStop { position: 0; color: "#537898" }
            GradientStop { position: 1; color: "#17283c" }
        }
    }

    Rectangle {
        id: topBar
        objectName: "canopyTopBar"
        anchors.top: parent.top
        width: parent.width
        height: canopyTheme.barHeight
        color: canopyTheme.chrome

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: 1
            color: "#3a5168"
            opacity: 0.65
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: root.compactLayout ? 14 : 22
            anchors.rightMargin: root.compactLayout ? 14 : 22
            spacing: root.compactLayout ? 12 : 20

            // Original, stylized white penguin silhouette, not Apple artwork.
            Canvas {
                id: tuxMark
                Layout.preferredWidth: 23
                Layout.preferredHeight: 28
                Accessible.name: "Canopy launcher placeholder"
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.fillStyle = "#f7f9fd"
                    ctx.beginPath()
                    ctx.ellipse(11.5, 15.5, 7.5, 11.8, 0, 0, 2 * Math.PI)
                    ctx.fill()
                    ctx.fillStyle = "#25354a"
                    ctx.beginPath()
                    ctx.ellipse(11.5, 18.5, 4.8, 7.5, 0, 0, 2 * Math.PI)
                    ctx.fill()
                    ctx.fillStyle = "#f7f9fd"
                    ctx.beginPath()
                    ctx.arc(9, 10, 1.3, 0, 2 * Math.PI)
                    ctx.arc(14, 10, 1.3, 0, 2 * Math.PI)
                    ctx.fill()
                    ctx.fillStyle = "#e7bd82"
                    ctx.beginPath()
                    ctx.moveTo(10, 12.5)
                    ctx.lineTo(13, 12.5)
                    ctx.lineTo(11.5, 15)
                    ctx.closePath()
                    ctx.fill()
                }
            }
            Label {
                text: "Canopy"
                color: canopyTheme.foreground
                font.pixelSize: 14
                font.bold: true
                font.family: "Sans Serif"
            }
            Label {
                text: "File"
                visible: !root.compactLayout
                color: canopyTheme.foreground
                font.pixelSize: 13
            }
            Label {
                text: "View"
                visible: !root.compactLayout
                color: canopyTheme.foreground
                font.pixelSize: 13
            }
            Item { Layout.fillWidth: true }
            Label {
                text: Qt.formatDateTime(new Date(), "ddd d MMM")
                color: canopyTheme.foreground
                font.pixelSize: 12
                font.weight: Font.Medium
            }
        }
    }

    // Dock controls are explicitly nonfunctional until session services exist.
    Rectangle {
        id: dock
        objectName: "canopyDock"
        width: Math.min(root.width - 32, dockRow.implicitWidth + 2 * canopyTheme.dockPadding)
        height: canopyTheme.dockSize
        radius: canopyTheme.cornerRadius
        color: canopyTheme.dockSurface
        border.color: canopyTheme.dockBorder
        border.width: 1
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 22
        clip: true

        Row {
            id: dockRow
            anchors.centerIn: parent
            spacing: canopyTheme.dockSpacing
            Repeater {
                model: [
                    { title: "Home" },
                    { title: "Search" },
                    { title: "Files" },
                    { title: "Settings" }
                ]
                delegate: DockTile {
                    required property var modelData
                    iconName: modelData.title
                }
            }
        }
    }

    Label {
        anchors.right: parent.right
        anchors.rightMargin: 21
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 9
        text: "CLASSIC PREVIEW"
        color: canopyTheme.muted
        opacity: 0.64
        font.pixelSize: 9
        font.letterSpacing: 2
        visible: root.width > 900
    }
}
