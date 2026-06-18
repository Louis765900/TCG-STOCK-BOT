import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App 1.0

// Compositeur : écrire un message Discord (embed) avec aperçu en direct.
Item {
    id: page
    property color couleur: Theme.accent
    property string statut: ""

    readonly property var palette: [Theme.accent, Theme.accent2, Theme.green,
                                    Theme.yellow, Theme.red, Theme.cyan, "#e30613"]

    // Convertit une couleur QML en "#RRGGBB" (sans canal alpha) pour Discord.
    function hexCouleur(c) {
        function h(x) { var v = Math.round(x * 255).toString(16); return v.length < 2 ? "0" + v : v }
        return "#" + h(c.r) + h(c.g) + h(c.b)
    }

    Connections {
        target: bridge
        function onMessageEnvoye(ok) {
            page.statut = ok ? "Message envoyé sur Discord ✓" : "Échec de l'envoi (vérifie la connexion dans Réglages)."
            statutTimer.restart()
        }
    }
    Timer { id: statutTimer; interval: 5000; onTriggered: page.statut = "" }

    RowLayout {
        anchors.fill: parent
        spacing: Theme.gap

        // ---- Formulaire ----------------------------------------------------
        Card {
            Layout.preferredWidth: parent.width * 0.52
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.gap

                Text { text: "Composer un message"; color: Theme.textHi
                       font { family: Theme.font; pixelSize: Theme.fsHead; weight: Font.DemiBold } }

                Field { id: fTitre; Layout.fillWidth: true; label: "Titre"; placeholder: "Ex : 🔥 Nouveau restock !" }

                // Description multiligne
                Text { text: "Description"; color: Theme.textDim
                       font { family: Theme.font; pixelSize: Theme.fsSmall; weight: Font.DemiBold } }
                ScrollView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 130
                    clip: true
                    background: Rectangle { radius: Theme.radiusSm; color: Theme.bg2
                                            border.width: 1; border.color: fDesc.activeFocus ? Theme.accent : Theme.border }
                    TextArea {
                        id: fDesc
                        color: Theme.text; selectByMouse: true; wrapMode: TextEdit.Wrap; padding: 12
                        placeholderText: "Texte du message (Markdown supporté)…"
                        placeholderTextColor: Theme.textDim
                        font { family: Theme.font; pixelSize: Theme.fsBody }
                        background: null
                    }
                }

                Field { id: fImage; Layout.fillWidth: true; label: "Image (URL)"; placeholder: "https://… (optionnel)" }
                RowLayout {
                    Layout.fillWidth: true; spacing: Theme.gap
                    Field { id: fUrl; Layout.fillWidth: true; label: "Lien du titre"; placeholder: "https://… (optionnel)" }
                    Field { id: fFooter; Layout.fillWidth: true; label: "Pied de page"; placeholder: "(optionnel)" }
                }

                // Couleur
                Text { text: "Couleur"; color: Theme.textDim
                       font { family: Theme.font; pixelSize: Theme.fsSmall; weight: Font.DemiBold } }
                Row {
                    spacing: 8
                    Repeater {
                        model: page.palette
                        delegate: Rectangle {
                            width: 28; height: 28; radius: 8
                            color: modelData
                            border.width: page.couleur == modelData ? 2 : 0
                            border.color: Theme.textHi
                            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                        onClicked: page.couleur = modelData }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                RowLayout {
                    Layout.fillWidth: true
                    Text { text: page.statut; color: page.statut.indexOf("✓") >= 0 ? Theme.green : Theme.red
                           wrapMode: Text.Wrap; Layout.fillWidth: true
                           font { family: Theme.font; pixelSize: Theme.fsSmall; weight: Font.DemiBold } }
                    AccentButton {
                        text: "Envoyer sur Discord"
                        onClicked: bridge.envoyerMessage({
                            "titre": fTitre.text,
                            "description": fDesc.text,
                            "couleur": page.hexCouleur(page.couleur),
                            "image_url": fImage.text,
                            "url": fUrl.text,
                            "footer": fFooter.text
                        })
                    }
                }
            }
        }

        // ---- Aperçu en direct ---------------------------------------------
        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#1a1d27"
            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.gap
                Text { text: "Aperçu"; color: Theme.textDim
                       font { family: Theme.font; pixelSize: Theme.fsSmall; weight: Font.DemiBold } }

                // Embed façon Discord (barre de couleur à gauche).
                Rectangle {
                    Layout.fillWidth: true
                    radius: 6
                    color: "#2b2d31"
                    implicitHeight: embedCol.implicitHeight + 24
                    Rectangle { width: 4; height: parent.height; radius: 2; color: page.couleur }
                    ColumnLayout {
                        id: embedCol
                        anchors { fill: parent; margins: 14; leftMargin: 18 }
                        spacing: 6
                        Text { visible: fTitre.text !== ""; text: fTitre.text; color: "#ffffff"
                               wrapMode: Text.Wrap; Layout.fillWidth: true
                               font { family: Theme.font; pixelSize: Theme.fsBody; weight: Font.Bold } }
                        Text { visible: fDesc.text !== ""; text: fDesc.text; color: "#dbdee1"
                               wrapMode: Text.Wrap; Layout.fillWidth: true
                               font { family: Theme.font; pixelSize: Theme.fsSmall } }
                        Rectangle {
                            visible: fImage.text !== ""
                            Layout.fillWidth: true; Layout.preferredHeight: 120
                            radius: 6; color: Theme.bg2
                            Image { anchors.fill: parent; source: fImage.text; fillMode: Image.PreserveAspectFit
                                    onStatusChanged: if (status === Image.Error) visible = false }
                        }
                        Text { visible: fFooter.text !== ""; text: fFooter.text; color: "#949ba4"
                               wrapMode: Text.Wrap; Layout.fillWidth: true
                               font { family: Theme.font; pixelSize: Theme.fsSmall } }
                    }
                }
                Item { Layout.fillHeight: true }
            }
        }
    }
}
