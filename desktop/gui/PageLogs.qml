import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App 1.0

// Journal en direct (ce que fait le bot), coloré par niveau, auto-défilement.
Item {
    id: page

    function couleurLigne(l) {
        if (l.indexOf("[ERROR]") >= 0 || l.indexOf("[CRITICAL]") >= 0) return Theme.red
        if (l.indexOf("[WARNING]") >= 0) return Theme.yellow
        if (l.indexOf("RESTOCK") >= 0 || l.indexOf("NOUVEAU") >= 0 || l.indexOf("DEAL") >= 0) return Theme.green
        return Theme.text
    }

    ListModel { id: logModel }

    function ajouter(ligne) {
        logModel.append({ ligne: ligne })
        if (logModel.count > 1000) logModel.remove(0, logModel.count - 1000)
        if (autoScroll.checked) liste.positionViewAtEnd()
    }

    Connections {
        target: bridge
        function onLogLine(l) { page.ajouter(l) }
    }
    Component.onCompleted: {
        var init = bridge.logsInitiaux()
        for (var i = 0; i < init.length; i++) logModel.append({ ligne: init[i] })
        liste.positionViewAtEnd()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.gap

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "Journal en direct"
                color: Theme.textHi
                font { family: Theme.font; pixelSize: Theme.fsHead; weight: Font.DemiBold }
            }
            Item { Layout.fillWidth: true }
            // Case auto-défilement
            Row {
                spacing: 8
                Rectangle {
                    id: autoScroll
                    property bool checked: true
                    width: 18; height: 18; radius: 5
                    color: checked ? Theme.accent : Theme.bg2
                    border.width: 1; border.color: checked ? Theme.accent : Theme.border
                    anchors.verticalCenter: parent.verticalCenter
                    Text { anchors.centerIn: parent; text: "✓"; color: Theme.bg0; font.pixelSize: 12; visible: parent.checked }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: parent.checked = !parent.checked }
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Suivre"
                    color: Theme.textDim
                    font { family: Theme.font; pixelSize: Theme.fsSmall }
                }
            }
            AccentButton {
                text: "Effacer"
                variant: "ghost"
                onClicked: logModel.clear()
            }
        }

        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            padding: 8
            ListView {
                id: liste
                anchors.fill: parent
                clip: true
                model: logModel
                spacing: 1
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
                delegate: Text {
                    width: liste.width
                    text: ligne
                    color: page.couleurLigne(ligne)
                    wrapMode: Text.WrapAnywhere
                    font { family: "Consolas, monospace"; pixelSize: Theme.fsSmall }
                    leftPadding: 6; rightPadding: 6; topPadding: 1; bottomPadding: 1
                }
            }
        }
    }
}
