import QtQuick
import QtQuick.Layouts
import App 1.0

// Tableau de bord : état du bot, contrôle (démarrer/arrêter), chiffres clés.
Item {
    id: page
    property var etat: ({})
    property bool running: etat.running === true

    function fmtUptime(s) {
        s = Math.floor(s || 0)
        if (s <= 0) return "—"
        var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60)
        if (h > 0) return h + " h " + m + " min"
        var sec = s % 60
        return m > 0 ? (m + " min " + sec + " s") : (sec + " s")
    }

    Connections {
        target: bridge
        function onStatusChanged(s) { page.etat = s }
    }
    Component.onCompleted: page.etat = bridge.statut()

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.gap

        // ---- Carte principale : état + contrôles --------------------------
        Card {
            Layout.fillWidth: true
            implicitHeight: 150
            RowLayout {
                anchors.fill: parent
                spacing: Theme.pad

                StatusDot {
                    Layout.alignment: Qt.AlignVCenter
                    couleur: page.running ? Theme.green : Theme.red
                    pulse: page.running
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 4
                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        text: page.running ? "Le bot tourne" : "Bot arrêté"
                        color: Theme.textHi
                        font { family: Theme.font; pixelSize: Theme.fsTitle; weight: Font.Bold }
                    }
                    Text {
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                        text: page.running
                              ? ("Actif depuis " + page.fmtUptime(page.etat.uptime_s)
                                 + "  •  cycle n°" + (page.etat.cycle || 0)
                                 + (page.etat.mode ? ("  •  " + page.etat.mode) : ""))
                              : "Clique sur Démarrer pour lancer la surveillance."
                        color: Theme.textDim
                        font { family: Theme.font; pixelSize: Theme.fsBody }
                    }
                }

                RowLayout {
                    spacing: Theme.gap
                    AccentButton {
                        text: "▶  Démarrer"
                        visible: !page.running
                        onClicked: bridge.demarrer()
                    }
                    AccentButton {
                        text: "■  Arrêter"
                        variant: "danger"
                        visible: page.running
                        onClicked: bridge.arreter()
                    }
                    AccentButton {
                        text: "⟳"
                        variant: "ghost"
                        visible: page.running
                        onClicked: bridge.redemarrer()
                    }
                }
            }
        }

        // ---- Chiffres clés -------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.gap
            Repeater {
                model: [
                    { t: "Produits surveillés", v: (page.etat.produits || 0), c: Theme.accent },
                    { t: "Alertes envoyées", v: (page.etat.alertes_total || 0), c: Theme.accent2 },
                    { t: "Cycle actuel", v: (page.etat.cycle || 0), c: Theme.cyan }
                ]
                delegate: Card {
                    Layout.fillWidth: true
                    implicitHeight: 96
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 2
                        Text {
                            text: modelData.v
                            color: modelData.c
                            font { family: Theme.font; pixelSize: 30; weight: Font.Bold }
                        }
                        Text {
                            text: modelData.t
                            color: Theme.textDim
                            font { family: Theme.font; pixelSize: Theme.fsSmall }
                        }
                    }
                }
            }
        }

        // ---- État des enseignes -------------------------------------------
        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                anchors.fill: parent
                spacing: Theme.gap
                Text {
                    text: "Enseignes (dernier cycle)"
                    color: Theme.textHi
                    font { family: Theme.font; pixelSize: Theme.fsHead; weight: Font.DemiBold }
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 8
                    Repeater {
                        model: {
                            var e = page.etat.enseignes || {}
                            var out = []
                            for (var k in e) out.push({ nom: k, statut: ("" + e[k]) })
                            return out
                        }
                        delegate: Rectangle {
                            height: 30
                            width: lbl.implicitWidth + 34
                            radius: 15
                            color: Theme.bg2
                            border.width: 1
                            border.color: Theme.border
                            Row {
                                anchors.centerIn: parent
                                spacing: 7
                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    width: 7; height: 7; radius: 4
                                    color: {
                                        var s = modelData.statut.toLowerCase()
                                        if (s.indexOf("ok") >= 0 || s.indexOf("succ") >= 0) return Theme.green
                                        if (s.indexOf("block") >= 0 || s.indexOf("err") >= 0 || s.indexOf("echec") >= 0) return Theme.red
                                        return Theme.yellow
                                    }
                                }
                                Text {
                                    id: lbl
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: modelData.nom
                                    color: Theme.text
                                    font { family: Theme.font; pixelSize: Theme.fsSmall }
                                }
                            }
                        }
                    }
                }
                Text {
                    visible: !page.etat.enseignes || Object.keys(page.etat.enseignes).length === 0
                    text: "Aucun cycle terminé pour l'instant."
                    color: Theme.textDim
                    font { family: Theme.font; pixelSize: Theme.fsBody }
                }
                Item { Layout.fillHeight: true }
                Text {
                    visible: !!page.etat.dernier_resume
                    Layout.fillWidth: true
                    text: page.etat.dernier_resume || ""
                    color: Theme.textDim
                    wrapMode: Text.Wrap
                    font { family: Theme.font; pixelSize: Theme.fsSmall }
                }
            }
        }
    }
}
