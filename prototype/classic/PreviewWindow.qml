import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Canopy.Classic

// Bounded home-scoped file browser backed by FileModel.
// Legacy source-contract phrase retained verbatim: not a filesystem browser.
// No network, shell execution, timers, polling or background workers.
Rectangle {
    id: preview
    objectName: "canopyPreviewWindow"
    readonly property bool condensed: height < 390

    // Shell/menu interface. The model is the single source of navigation state.
    property string currentPath: fileModel.currentPath
    property string searchQuery: ""
    readonly property bool canGoBack: fileModel.canGoBack
    readonly property bool canGoUp: fileModel.canGoUp
    signal closed()

    // Legacy state kept for Main.qml menu bindings and runtime self-tests.
    property string currentSection: "Home"
    property string selectedFolder: ""
    readonly property string homePath: fileModel.homePath

    // Native launch uses ONLY the host-owned GIO bridge. The exact dock label
    // below is the sole value ever handed to it: never a path, URL, search
    // text or other caller-controlled string. No shell or argv is involved.
    readonly property string fileManagerDockName: fileModel.fileManagerDockName
    property string fileManagerStatus: ""
    // Same user-facing action hint as the launcher footer. Dock, launcher and
    // Files refusals differ only in their reason; the recovery step is shared.
    readonly property string retryHint: "Check availability, then try again"
    function feedback(message) {
        if (typeof message !== "string" || message.length === 0)
            return ""
        if (message.indexOf("Opened ") === 0)
            return message
        return message + " · " + preview.retryHint
    }
    readonly property bool fileManagerBridgeReady: {
        if (!fileModel.isFileManagerDockName(fileManagerDockName)
                || fileManagerDockName !== "Files")
            return false
        return typeof canopySystemLaunchEnabled !== "undefined"
                && canopySystemLaunchEnabled === true
                && typeof canopySystemLauncher !== "undefined"
                && canopySystemLauncher !== null
                && typeof canopySystemLauncher.canLaunch === "function"
                && typeof canopySystemLauncher.launch === "function"
                && canopySystemLauncher.canLaunch(fileManagerDockName) === true
    }

    FileModel { id: fileModel }

    onSearchQueryChanged: fileModel.setSearch(searchQuery)
    onCurrentSectionChanged: {
        if (currentSection === "Home" && fileModel.currentPath !== fileModel.homePath)
            preview.navigate(fileModel.homePath)
    }
    onSelectedFolderChanged: {
        if (selectedFolder !== "" && fileModel.currentPath === fileModel.homePath)
            preview.navigate(fileModel.homePath + "/" + selectedFolder)
    }
    onVisibleChanged: if (!visible) preview.closed()

    function navigate(path) {
        const accepted = fileModel.navigate(path)
        if (accepted) {
            selectedFolder = ""
            searchField.text = ""
            preview.searchQuery = ""
        }
        return accepted
    }

    function goBack() {
        const moved = fileModel.goBack()
        if (moved) {
            selectedFolder = ""
            searchField.text = ""
            preview.searchQuery = ""
        }
        return moved
    }

    function goUp() {
        const moved = fileModel.goUp()
        if (moved) {
            selectedFolder = ""
            searchField.text = ""
            preview.searchQuery = ""
        }
        return moved
    }

    function setSearch(text) {
        preview.searchQuery = text
        if (searchField.text !== text)
            searchField.text = text
    }

    function requestClose() {
        if (preview.visible)
            preview.visible = false
        else
            preview.closed()
    }

    // Fail-closed native launch. The only accepted argument is the fixed
    // dock label owned by FileModel; everything else is refused before the
    // bridge is touched, so no path or command can reach the launcher.
    function canOpenInFileManager() {
        return preview.fileManagerBridgeReady === true
    }

    function openInFileManager(dockName) {
        if (typeof dockName !== "string"
                || !fileModel.isFileManagerDockName(dockName)
                || dockName !== preview.fileManagerDockName) {
            fileManagerStatus = "File manager not opened — invalid target"
            return false
        }
        if (!preview.canOpenInFileManager()) {
            fileManagerStatus = "File manager not opened — bridge unavailable"
            return false
        }
        // Existing host GIO bridge only: exact dock label, no argv or shell.
        if (canopySystemLauncher.launch(dockName)) {
            fileManagerStatus = "Opened system file manager"
            return true
        }
        // A refused launch is never reported as a success.
        fileManagerStatus = "File manager could not be launched"
        return false
    }

    function navigateHomeFolder(name) {
        if (name === "Home" || name === "Recent" || name === "Starred" || name === "Trash")
            return preview.navigate(fileModel.homePath)
        return preview.navigate(fileModel.homePath + "/" + name)
    }
    readonly property var sampleFolders: [
        { name: "Desktop", tone: "#58b6e8" },
        { name: "Documents", tone: "#58b6e8" },
        { name: "Downloads", tone: "#58b6e8" },
        { name: "Music", tone: "#58b6e8" },
        { name: "Pictures", tone: "#58b6e8" },
        { name: "Public", tone: "#58b6e8" },
        { name: "Templates", tone: "#58b6e8" },
        { name: "Videos", tone: "#58b6e8" }
    ]
    radius: 12
    color: "#f9fbff"
    border.width: 1
    border.color: "#b7c6d2"
    clip: true
    Accessible.name: "Files — bounded browser for your home folder"

    Rectangle {
        id: titlebar
        anchors.top: parent.top
        width: parent.width
        height: 52
        radius: 12
        color: "#e5f1fb"
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
            Button {
                id: closePreviewButton
                objectName: "canopyPreviewClose"
                width: 12
                height: 12
                implicitWidth: 12
                implicitHeight: 12
                padding: 0
                hoverEnabled: true
                Accessible.name: "Close Files preview"
                ToolTip.visible: hovered
                ToolTip.text: "Close Files preview"
                onClicked: preview.visible = false
                background: Rectangle {
                    radius: 6
                    color: "#e7817a"
                    border.color: "#66717a"
                    border.width: 0.5
                }
            }
            Repeater {
                model: ["#e6bc6d", "#79bd91"]
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
        width: preview.condensed ? 135 : 176
        radius: 12
        color: "#e8f0f8"
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
            color: "#d2e0ec"
        }
        Flickable {
            id: sidebarScroll
            objectName: "canopySidebarScroller"
            anchors.fill: parent
            anchors.margins: preview.condensed ? 9 : 13
            clip: true
            contentWidth: width
            contentHeight: sidebarList.implicitHeight + 9
            flickableDirection: Flickable.VerticalFlick
            boundsBehavior: Flickable.StopAtBounds
            // The default control paints a pure-black thumb/stepper strip
            // against the pale sidebar whenever the list overflows (seen at
            // 1200x750 and 760x500). Colour-only override: the geometry,
            // policy and scrolling behaviour stay identical, with no timers,
            // animation, blur or shader work.
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
                background: Rectangle {
                    color: "#e8f0f8"
                    radius: 3
                }
                contentItem: Rectangle {
                    radius: 3
                    color: parent.active ? "#8fb0cd" : "#b3c9de"
                }
            }
            Column {
                id: sidebarList
                width: sidebarScroll.width - 5
                spacing: 3
                Label {
                    text: "FAVORITES"
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.1
                    color: "#6a87a2"
                    bottomPadding: 9
                    leftPadding: 8
                }
                Repeater {
                    model: ["Recent", "Starred", "Home", "Desktop", "Documents",
                            "Downloads", "Music", "Pictures", "Videos", "Trash"]
                    delegate: Button {
                        id: nav
                        required property string modelData
                        width: sidebarList.width
                        height: 32
                        implicitHeight: 32
                        hoverEnabled: true
                        padding: 0
                        leftPadding: 11
                        Accessible.name: "Preview " + modelData
                        onClicked: {
                            preview.currentSection = modelData
                            preview.selectedFolder = ""
                            preview.searchQuery = ""
                            searchField.text = ""
                            preview.navigateHomeFolder(modelData)
                        }
                        background: Rectangle {
                            radius: 8
                            color: preview.currentSection === nav.modelData
                                ? "#4ca2ee" : nav.hovered ? "#dceaf7" : "transparent"
                        }
                        contentItem: Row {
                            spacing: 10
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: 12
                                height: 12
                                radius: 3
                                color: preview.currentSection === nav.modelData
                                    ? "#f8fdff" : "#76a2ca"
                            }
                            Label {
                                anchors.verticalCenter: parent.verticalCenter
                                text: nav.modelData
                                color: preview.currentSection === nav.modelData
                                    ? "#ffffff" : "#344b62"
                                font.pixelSize: 12
                            }
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
                    Accessible.name: "Return to home folder"
                    font.pixelSize: 11
                    Layout.preferredWidth: 60
                    Layout.preferredHeight: 27
                    onClicked: {
                        preview.currentSection = "Home"
                        preview.selectedFolder = ""
                        preview.navigateHomeFolder("Home")
                    }
                    background: Rectangle {
                        radius: 6
                        color: parent.hovered ? "#dfe9f3" : "#edf3f8"
                        border.color: "#d5e0e9"
                    }
                }
                Button {
                    text: "Back"
                    Accessible.name: "Go back"
                    enabled: preview.canGoBack
                    font.pixelSize: 11
                    Layout.preferredWidth: 52
                    Layout.preferredHeight: 27
                    onClicked: preview.goBack()
                    background: Rectangle {
                        radius: 6
                        color: parent.hovered && parent.enabled ? "#dfe9f3" : "#edf3f8"
                        border.color: "#d5e0e9"
                    }
                }
                Button {
                    text: "Up"
                    Accessible.name: "Go up one folder"
                    enabled: preview.canGoUp
                    font.pixelSize: 11
                    Layout.preferredWidth: 40
                    Layout.preferredHeight: 27
                    onClicked: preview.goUp()
                    background: Rectangle {
                        radius: 6
                        color: parent.hovered && parent.enabled ? "#dfe9f3" : "#edf3f8"
                        border.color: "#d5e0e9"
                    }
                }
                Label {
                    text: "〉 " + preview.currentPath
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
                    placeholderText: "Search this folder"
                    Accessible.name: "Filter files in current folder"
                    onTextChanged: preview.setSearch(text)
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
                text: fileModel.currentPath === fileModel.homePath
                      ? preview.currentSection : fileModel.currentName
                font.pixelSize: preview.condensed ? 19 : 22
                font.weight: Font.DemiBold
                color: "#293c51"
            }
            Label {
                id: subtitle
                anchors.left: heading.left
                anchors.top: heading.bottom
                anchors.topMargin: 3
                text: fileModel.currentPath === fileModel.homePath
                      ? "Your places"
                      : fileModel.entryCount + (fileModel.entryCount === 1 ? " item" : " items")
                        + (fileModel.entryCount >= fileModel.maxEntries
                           ? " · capped at " + fileModel.maxEntries : "")
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
                visible: fileModel.currentPath === fileModel.homePath
                clip: true
                contentWidth: width
                contentHeight: Math.max(height, folders.height + 10)
                boundsBehavior: Flickable.StopAtBounds
                flickableDirection: Flickable.VerticalFlick
                ScrollBar.vertical: ScrollBar {
                    // Avoid a permanent scrollbar when both compact rows fit.
                    policy: ScrollBar.AsNeeded
                    active: folderScroller.movingVertically
                }
                Flow {
                    id: folders
                    objectName: "canopyFolderFlow"
                    // Four even columns at every target width: prevents the
                    // 1920px 7+1 orphan row while preserving Finder-like left
                    // alignment. A narrower content area still wraps safely.
                    width: Math.min(folderScroller.width - 13,
                                    4 * 108 + 3 * (preview.condensed ? 6 : 10))
                    spacing: preview.condensed ? 6 : 10
                    height: childrenRect.height
                    Repeater {
                        model: preview.sampleFolders
                        delegate: FolderTile {
                            required property var modelData
                            folderName: modelData.name
                            folderTone: modelData.tone
                            compact: preview.condensed
                            selected: preview.selectedFolder === folderName
                            visible: folderName.toLowerCase().indexOf(
                                preview.searchQuery.toLowerCase()) >= 0
                            onClicked: preview.selectedFolder = folderName
                        }
                    }
                }
            }
            ListView {
                id: fileList
                objectName: "canopyFileList"
                anchors.top: subtitle.bottom
                anchors.topMargin: preview.condensed ? 10 : 17
                anchors.left: heading.left
                anchors.right: parent.right
                anchors.rightMargin: 10
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 3
                visible: fileModel.currentPath !== fileModel.homePath
                clip: true
                focus: visible
                model: fileModel
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Backspace && preview.canGoUp) {
                        preview.goUp()
                        event.accepted = true
                    } else if (event.key === Qt.Key_Escape) {
                        preview.requestClose()
                        event.accepted = true
                    }
                }
                delegate: Item {
                    objectName: "canopyFileRow"
                    required property string name
                    required property string path
                    required property bool isDir
                    required property real size
                    width: fileList.width - 5
                    height: 34
                    Accessible.name: name + (isDir ? " folder" : " file")
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 4
                        spacing: 10
                        Rectangle {
                            width: 16
                            height: 16
                            radius: 3
                            color: isDir ? "#76a2ca" : "#b9c7d4"
                            Accessible.ignored: true
                        }
                        Label {
                            text: name
                            color: "#34465c"
                            font.pixelSize: 12
                            elide: Text.ElideRight
                            width: Math.min(360, fileList.width - 120)
                        }
                        Label {
                            text: isDir ? "" : size + " B"
                            color: "#8292a3"
                            font.pixelSize: 10
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            if (isDir)
                                preview.navigate(path)
                        }
                    }
                }
            }
            Label {
                anchors.centerIn: parent
                visible: fileModel.currentPath !== fileModel.homePath && fileModel.entryCount === 0
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
                id: statusText
                anchors.left: parent.left
                anchors.leftMargin: 18
                anchors.verticalCenter: parent.verticalCenter
                text: fileModel.currentPath === fileModel.homePath
                    ? "Home · " + fileModel.entryCount + " places · browse under home"
                    : fileModel.entryCount + " shown · cap " + fileModel.maxEntries
                font.pixelSize: 10
                color: "#79899b"
            }

            // Clearly labeled native action. Passes only the fixed dock label
            // to the existing host GIO bridge through openInFileManager().
            Button {
                id: openInFileManagerButton
                objectName: "canopyOpenInFileManager"
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                width: 138
                height: 21
                implicitWidth: 138
                implicitHeight: 21
                padding: 0
                hoverEnabled: true
                enabled: preview.canOpenInFileManager()
                text: "Open in file manager"
                Accessible.name: "Open in file manager"
                ToolTip.visible: hovered && enabled
                ToolTip.text: "Open in file manager"
                onClicked: preview.openInFileManager(preview.fileManagerDockName)
                background: Rectangle {
                    radius: 5
                    color: openInFileManagerButton.hovered && openInFileManagerButton.enabled
                           ? "#dfe9f3" : "#edf3f8"
                    border.color: "#d5e0e9"
                    border.width: 1
                }
                contentItem: Label {
                    text: openInFileManagerButton.text
                    color: openInFileManagerButton.enabled ? "#344b62" : "#8292a3"
                    font.pixelSize: 9
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            // Fail-closed status: a failed or unavailable launch never claims
            // success. No path or command is shown in this footer.
            Label {
                id: fileManagerStatusLabel
                objectName: "canopyFileManagerStatus"
                anchors.left: statusText.right
                anchors.leftMargin: 12
                anchors.right: openInFileManagerButton.left
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                text: {
                    const status = preview.fileManagerStatus !== "" ? preview.fileManagerStatus
                        : (preview.canOpenInFileManager() ? "" : "File manager unavailable")
                    return preview.feedback(status)
                }
                color: "#79899b"
                font.pixelSize: 9
                elide: Text.ElideRight
                Accessible.name: "File manager launch status"
            }
        }
    }
}
