import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import App 1.0

// Surveillance : la liste des produits suivis (watchlist) + suppression.
Item {
    id: page

    ListModel { id: wlModel }

    function remplir(liste) {
        wlModel.clear()
        for (var i = 0; i < liste.length; i++) {
            var p = liste[i]
            wlModel.append({
                url: "" + (p.url || ""),
                titre: "" + (p.titre || ""),
                enseigne: "" + (p.enseigne || ""),
                prix: "" + (p.prix || "N/A"),
                enStock: (p.en_stock === 1 || p.en_stock === true)
            })
        }
    }

    Connections {
        target: bridge
        function onWatchlistChanged(liste) { page.remplir(liste) }
    }
    Component.onCompleted: bridge.rafraichirWatchlist()

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.gap

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "Produits surveillés"
                color: Theme.textHi
                font { family: Theme.font; pixelSize: Theme.fsHead; weight: Font.DemiBold }
            }
            Rectangle {
                radius: 11; height: 22; width: cnt.implicitWidth + 18
                color: Theme.bg2; border.width: 1; border.color: Theme.border
                Text { id: cnt; anchors.centerIn: parent; text: wlModel.count
                       color: Theme.textDim; font { family: Theme.font; pixelSize: Theme.fsSmall } }
            }
            Item { Layout.fillWidth: true }
            AccentButton { text: "Rafraîchir"; variant: "ghost"; onClicked: bridge.rafraichirWatchlist() }
        }

        Card {
            Layout.fillWidth: true
            Layout.fillHeight: true
            padding: 8

            ListView {
                id: liste
                anchors.fill: parent
                clip: true
                model: wlModel
                spacing: 6
                boundsBehavior: Flickable.StopAtBounds
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                delegate: Rectangle {
                    width: liste.width - 8
                    height: 56
                    radius: Theme.radiusSm
                    color: rowMa.containsMouse ? Theme.bg2 : "transparent"
                    Behavior on color { ColorAnimation { duration: Theme.anim } }
                    MouseArea { id: rowMa; anchors.fill: parent; hoverEnabled: true }

                    RowLayout {
                        anchors { fill: parent; leftMargin: 12; rightMargin: 8 }
                        spacing: 12

                        Rectangle {
                            width: 8; height: 8; radius: 4
                            color: enStock ? Theme.green : Theme.textDim
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: titre
                                color: Theme.text
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                                font { family: Theme.font; pixelSize: Theme.fsBody }
                            }
                            Text {
                                text: enseigne + "  •  " + (enStock ? "En stock" : "Épuisé")
                                color: Theme.textDim
                                font { family: Theme.font; pixelSize: Theme.fsSmall }
                            }
                        }
                        Text {
                            text: prix
                            color: Theme.accent
                            font { family: Theme.font; pixelSize: Theme.fsBody; weight: Font.DemiBold }
                        }
                        AccentButton {
                            text: "🗑"
                            variant: "ghost"
                            implicitWidth: 40
                            onClicked: bridge.supprimerProduit(url)
                        }
                    }
                }

                // État vide
                Text {
                    anchors.centerIn: parent
                    visible: wlModel.count === 0
                    text: "Aucun produit suivi pour l'instant.\nLance la surveillance depuis l'accueil."
                    horizontalAlignment: Text.AlignHCenter
                    color: Theme.textDim
                    font { family: Theme.font; pixelSize: Theme.fsBody }
                }
            }
        }
    }
}
