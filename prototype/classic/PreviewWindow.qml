import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Self-contained interactive design preview, not a filesystem browser.
// Sidebar selection, sample-folder selection, and searching only affect local
// demo data. No disk reads, network access, shell commands or background jobs.
Rectangle {
    id: preview
    objectName: "canopyPreviewWindow"
    readonly property bool condensed: height < 390
    property string currentSection: "Home"
    property string selectedFolder: ""
    property string searchQuery: ""
    readonly property var sampleFolders: [
        { name: "Documents", tone: "#6b9ec9" },
        { name: "Pictures", tone: "#9b93d0" },
        { name: "Music", tone: "#d4a078" },
        { name: "Projects", tone: "#7cad9f" },
        { name: "Downloads", tone: "#819fd0" },
        { name: "Shared", tone: "#ba93ad" }
    ]
    radius: 12
    color: "#fcfdff"
    border.width: 1
    border.color: "#b7c6d2"
    clip: true
    Accessible.name: "Files interface demonstration. Not connected to the filesystem."

    Rectangle {
        id: titlebar
        anchors.top: parent.top
        width: parent.width
        height: 52
        radius: 12
        color: "#eff3f7"
        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: parent.height - 12
            color: titlebar.color
        }
        Row {
            anchors.left: parent.left
            anchors.leftMargin: 18
            anchors.verticalCenter: parent.verticalCenter
            spacing: 8
            Repeater {
                model: ["#e7817a", "#e6bc6d", "#79bd91"]
                delegate: Rectangle {
                    required property string modelData
                    width: 12
                    height: 12
                    radius: 6
                    color: modelData
                    border.color: "#66717a"
                    border.width: 0.5
                }
            }
        }
        Label {
            anchors.centerIn: parent
            text: "Files"
            font.pixelSize: 13
            font.weight: Font.DemiBold
            color: "#425368"
        }
        Rectangle {
            anchors.bottom: parent.bottom
            height: 1
            width: parent.width
            color: "#d7e0e8"
        }
    }

    Rectangle {
        id: sidebar
        anchors.top: titlebar.bottom
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        width: preview.condensed ? 135 : 170
        radius: 12
        color: "#edf2f7"
        Rectangle {
            anchors.top: parent.top
            width: parent.width
            height: parent.height - 12
            color: sidebar.color
        }
        Rectangle {
            anchors.right: parent.right
            width: 1
            height: parent.height
            color: "#d9e1e9"
        }
        Column {
            anchors.fill: parent
            anchors.margins: preview.condensed ? 10 : 15
            spacing: 5
            Label {
                text: "FAVORITES"
                font.pixelSize: 10
                font.weight: Font.DemiBold
                font.letterSpacing: 1.1
                color: "#788ba0"
                bottomPadding: 9
                leftPadding: 6
            }
            Repeater {
                model: ["Home", "Documents", "Pictures", "Downloads"]
                delegate: Button {
                    id: nav
                    required property string modelData
                    width: parent.width
                    height: 33
                    implicitHeight: 33
                    hoverEnabled: true
                    padding: 0
                    leftPadding: 9
                    Accessible.name: "Preview " + modelData
                    onClicked: {
                        preview.currentSection = modelData
                        preview.selectedFolder = ""
                        preview.searchQuery = ""
                        searchField.text = ""
                    }
                    background: Rectangle {
                        radius: 7
                        color: preview.currentSection === nav.modelData
                            ? "#d8e7f6" : nav.hovered ? "#e3ebf4" : "transparent"
                    }
                    contentItem: Row {
                        spacing: 10
                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 12
                            height: 12
                            radius: 3
                            color: preview.currentSection === nav.modelData ? "#5b8bbd" : "#91a5b9"
                        }
                        Label {
                            anchors.verticalCenter: parent.verticalCenter
                            text: nav.modelData
                            color: "#36495e"
                            font.pixelSize: 12
                        }
                    }
                }
            }
        }
    }

    Item {
        id: mainArea
        anchors.top: titlebar.bottom
        anchors.left: sidebar.right
        anchors.bottom: parent.bottom
        anchors.right: parent.right

        Rectangle {
            id: toolbar
            anchors.top: parent.top
            width: parent.width
            height: preview.condensed ? 0 : 44
            visible: !preview.condensed
            color: "#fafcff"
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: "#e7edf3"
            }
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 17
                anchors.rightMargin: 17
                spacing: 10
                Button {
                    text: "Home"
                    Accessible.name: "Return to sample home"
                    font.pixelSize: 11
                    Layout.preferredWidth: 60
                    Layout.preferredHeight: 27
                    onClicked: {
                        preview.currentSection = "Home"
                        preview.selectedFolder = ""
                    }
                    background: Rectangle {
                        radius: 6
                        color: parent.hovered ? "#dfe9f3" : "#edf3f8"
                        border.color: "#d5e0e9"
                    }
                }
                Label {
                    text: "〉 " + preview.currentSection
                    color: "#566b80"
                    font.pixelSize: 12
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
                TextField {
                    id: searchField
                    objectName: "canopyPreviewSearch"
                    Layout.preferredWidth: Math.min(194, mainArea.width * 0.34)
                    Layout.preferredHeight: 28
                    font.pixelSize: 11
                    placeholderText: "Search demo folders"
                    Accessible.name: "Filter sample folder names"
                    onTextChanged: preview.searchQuery = text
                    background: Rectangle {
                        radius: 7
                        color: "#ffffff"
                        border.color: searchField.activeFocus ? "#6597c4" : "#d1dce6"
                        border.width: 1
                    }
                }
            }
        }

        Item {
            id: contentArea
            anchors.top: toolbar.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: statusBar.top

            Label {
                id: heading
                anchors.left: parent.left
                anchors.leftMargin: preview.condensed ? 17 : 23
                anchors.top: parent.top
                anchors.topMargin: preview.condensed ? 13 : 17
                text: preview.currentSection
                font.pixelSize: preview.condensed ? 19 : 22
                font.weight: Font.DemiBold
                color: "#293c51"
            }
            Label {
                id: subtitle
                anchors.left: heading.left
                anchors.top: heading.bottom
                anchors.topMargin: 3
                text: preview.currentSection === "Home"
                      ? "Your places" : "This section is a visual preview"
                color: "#8292a3"
                font.pixelSize: 11
            }

            Flickable {
                id: folderScroller
                objectName: "canopyFolderScroller"
                anchors.top: subtitle.bottom
                anchors.topMargin: preview.condensed ? 10 : 17
                anchors.left: heading.left
                anchors.right: parent.right
                anchors.rightMargin: 10
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 3
                visible: preview.currentSection === "Home"
                clip: true
                contentWidth: width
                contentHeight: Math.max(height, folders.height + 10)
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                ScrollBar.vertical: ScrollBar {
                    policy: preview.condensed ? ScrollBar.AlwaysOn : ScrollBar.AsNeeded
                    active: preview.condensed
                }
                Flow {
                    id: folders
                    width: folderScroller.width - 13
                    spacing: preview.condensed ? 6 : 10
                    height: childrenRect.height
                    Repeater {
                        model: preview.sampleFolders
                        delegate: FolderTile {
                            required property var modelData
                            folderName: modelData.name
                            folderTone: modelData.tone
                            selected: preview.selectedFolder === folderName
                            visible: folderName.toLowerCase().indexOf(
                                preview.searchQuery.toLowerCase()) >= 0
                            onClicked: preview.selectedFolder = folderName
                        }
                    }
                }
            }
            Label {
                anchors.centerIn: parent
                visible: preview.currentSection !== "Home"
                text: "No local files are loaded in this preview."
                color: "#75869a"
                font.pixelSize: 12
            }

        }

        Rectangle {
            id: statusBar
            anchors.bottom: parent.bottom
            width: parent.width
            height: 27
            radius: 12
            color: "#f9fbfd"
            Rectangle {
                anchors.top: parent.top
                width: parent.width
                height: parent.height - 12
                color: statusBar.color
            }
            Rectangle {
                width: parent.width
                height: 1
                color: "#e6edf2"
            }
            Label {
                anchors.left: parent.left
                anchors.leftMargin: 18
                anchors.verticalCenter: parent.verticalCenter
                text: preview.selectedFolder !== ""
                    ? preview.selectedFolder + " selected · demo only"
                    : preview.currentSection === "Home" ? "6 sample folders · no disk access"
                    : "Preview only · no disk access"
                font.pixelSize: 10
                color: "#79899b"
            }
        }
    }
}
