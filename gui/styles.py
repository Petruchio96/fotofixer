"""
Application stylesheet constants.
"""

APP_STYLESHEET = """
QMainWindow, QWidget#centralSurface {
    background: #eef3f8;
    color: #162131;
}
QMenuBar {
    background: #f6f9fc;
    border-bottom: 1px solid #d6dfe8;
    padding: 4px 8px;
}
QMenuBar::item {
    background: transparent;
    padding: 6px 10px;
    border-radius: 6px;
}
QMenuBar::item:selected {
    background: #dde8f3;
}
QMenu {
    background: #ffffff;
    border: 1px solid #d4dde7;
    padding: 6px;
}
QMenu::item {
    padding: 8px 16px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: #e4eef9;
}
QFrame#panel {
    background: #fbfdff;
    border: 1px solid #d6dfe8;
    border-radius: 18px;
}
QLabel#windowTitle {
    font-size: 28px;
    font-weight: 700;
    color: #102033;
}
QLabel#windowSubtitle {
    font-size: 13px;
    color: #556579;
}
QLabel#sectionTitle {
    font-size: 18px;
    font-weight: 700;
    color: #112033;
}
QLabel#sourceFileLabel {
    font-size: 13px;
    font-weight: 700;
    color: #162131;
    min-height: 22px;
}
QLabel#sourceSummary {
    color: #26425f;
    background: #eef4fb;
    border: 1px solid #d8e4f0;
    border-radius: 10px;
    padding: 10px 12px;
    font-weight: 600;
}
QLabel#sectionNote {
    color: #5a697c;
    font-size: 12px;
    line-height: 1.4em;
}
QLabel#sourceHint {
    color: #617084;
    background: #f5f8fb;
    border: 1px dashed #ccd7e2;
    border-radius: 12px;
    padding: 12px 14px;
}
QPushButton {
    background: #ffffff;
    color: #102033;
    border: 1px solid #cad6e2;
    border-radius: 10px;
    padding: 10px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background: #f3f8fe;
    border-color: #a9bfd7;
}
QPushButton:pressed {
    background: #e7f0fa;
}
QPushButton:disabled {
    color: #8c9aa8;
    background: #f5f7f9;
    border-color: #d7dee5;
}
QPushButton#accentButton {
    background: #d97706;
    color: white;
    border: 1px solid #d97706;
    padding: 12px 18px;
}
QPushButton#accentButton:disabled {
    color: #8c9aa8;
    background: #f5f7f9;
    border-color: #d7dee5;
}
QPushButton#accentButton:hover {
    background: #b85f00;
    border-color: #b85f00;
}
QPushButton#accentButton:pressed {
    background: #9a4f00;
    border-color: #9a4f00;
}
QPushButton#applyButton[tone="safe"] {
    background: #1f6feb;
    color: white;
    border-color: #1f6feb;
}
QPushButton#applyButton[tone="safe"]:disabled,
QPushButton#applyButton[tone="warning"]:disabled {
    color: #8c9aa8;
    background: #f5f7f9;
    border-color: #d7dee5;
}
QPushButton#applyButton[tone="safe"]:hover {
    background: #165dc5;
    border-color: #165dc5;
}
QPushButton#applyButton[tone="warning"] {
    background: #c24141;
    color: white;
    border-color: #c24141;
}
QPushButton#applyButton[tone="warning"]:hover {
    background: #a83333;
    border-color: #a83333;
}
QPushButton#applyButton[tone="warning"]:pressed {
    background: #8f2a2a;
    border-color: #8f2a2a;
}
QPushButton[tone="danger"] {
    background: #c24141;
    color: white;
    border-color: #c24141;
}
QPushButton[tone="danger"]:hover {
    background: #a83333;
    border-color: #a83333;
}
QPushButton[tone="danger"]:pressed {
    background: #8f2a2a;
    border-color: #8f2a2a;
}
QPushButton[tone="danger"]:disabled,
QPushButton[tone="primary"]:disabled,
QPushButton[tone="neutral"]:disabled {
    color: #8c9aa8;
    background: #f5f7f9;
    border-color: #d7dee5;
}
QPushButton[tone="primary"] {
    background: #e8f1ff;
    color: #1459bd;
    border-color: #8cb7f0;
}
QPushButton[tone="primary"]:hover {
    background: #dcebff;
    border-color: #6ea1e8;
}
QPushButton[tone="primary"]:pressed {
    background: #c8ddff;
    border-color: #4f8be0;
}
QPushButton[tone="neutral"] {
    background: #ffffff;
    color: #102033;
    border: 1px solid #cad6e2;
}
QGroupBox {
    background: #ffffff;
    border: 1px solid #d8e1ea;
    border-radius: 14px;
    margin-top: 12px;
    padding: 14px 16px 16px 16px;
    font-weight: 700;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #31445a;
}
QLineEdit {
    min-height: 36px;
    padding: 0 12px;
    background: #ffffff;
    border: 1px solid #cdd8e3;
    border-radius: 10px;
    selection-background-color: #c8ddff;
}
QLineEdit:focus {
    border: 1px solid #1f6feb;
}
QLabel#sourceThumbnail {
    background: #f7fafc;
    border: 1px solid #d8e1ea;
    border-radius: 14px;
    padding: 10px;
}
QRadioButton {
    color: #23384f;
    spacing: 8px;
    font-weight: 600;
}
QListWidget#selectedPhotosList {
    background: #ffffff;
    border: 1px solid #d8e1ea;
    border-radius: 12px;
    padding: 8px;
    outline: none;
}
QLabel#selectedPhotosEmpty {
    color: #617084;
    background: #ffffff;
    border: 1px dashed #ccd7e2;
    border-radius: 12px;
    padding: 16px;
}
QListWidget#thumbnailGrid {
    background: transparent;
    border: none;
    padding: 4px 12px 12px 12px;
    outline: none;
}
QListWidget#thumbnailGrid::item {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 14px;
    padding: 8px;
    margin: 4px;
}
QListWidget#thumbnailGrid::item:hover {
    background: #f4f8fc;
    border-color: #d5e2ef;
}
QListWidget#thumbnailGrid::item:selected {
    background: #fff3e3;
    border: 2px solid #d97706;
    color: #4a2a00;
}
QLabel#thumbnailGroupHeader {
    color: #4d6177;
    font-weight: 700;
    padding-left: 2px;
}
QLabel#thumbnailGroupHeader[group="gps"],
QLabel#groupDot[group="gps"] {
    color: #1f5fc4;
}
QLabel#thumbnailGroupHeader[group="no_gps"],
QLabel#groupDot[group="no_gps"] {
    color: #a15c07;
}
QFrame#groupDivider {
    background: #d6dfe8;
    border: none;
}
QListWidget#thumbnailGrid QScrollBar:vertical,
QListWidget#selectedPhotosList QScrollBar:vertical {
    background: #eef3f8;
    width: 14px;
    margin: 8px 2px 8px 2px;
    border-radius: 7px;
}
QListWidget#thumbnailGrid QScrollBar::handle:vertical,
QListWidget#selectedPhotosList QScrollBar::handle:vertical {
    background: #c4cfdb;
    min-height: 36px;
    border-radius: 7px;
}
QListWidget#thumbnailGrid QScrollBar::handle:vertical:hover,
QListWidget#selectedPhotosList QScrollBar::handle:vertical:hover {
    background: #b3c0ce;
}
QListWidget#thumbnailGrid QScrollBar::add-line:vertical,
QListWidget#thumbnailGrid QScrollBar::sub-line:vertical,
QListWidget#selectedPhotosList QScrollBar::add-line:vertical,
QListWidget#selectedPhotosList QScrollBar::sub-line:vertical {
    background: transparent;
    height: 0px;
}
QListWidget#thumbnailGrid QScrollBar::add-page:vertical,
QListWidget#thumbnailGrid QScrollBar::sub-page:vertical,
QListWidget#selectedPhotosList QScrollBar::add-page:vertical,
QListWidget#selectedPhotosList QScrollBar::sub-page:vertical {
    background: transparent;
}
QListWidget#thumbnailGrid QScrollBar:horizontal,
QListWidget#selectedPhotosList QScrollBar:horizontal {
    background: #eef3f8;
    height: 14px;
    margin: 2px 8px 2px 8px;
    border-radius: 7px;
}
QListWidget#thumbnailGrid QScrollBar::handle:horizontal,
QListWidget#selectedPhotosList QScrollBar::handle:horizontal {
    background: #c4cfdb;
    min-width: 36px;
    border-radius: 7px;
}
QListWidget#thumbnailGrid QScrollBar::handle:horizontal:hover,
QListWidget#selectedPhotosList QScrollBar::handle:horizontal:hover {
    background: #b3c0ce;
}
QListWidget#thumbnailGrid QScrollBar::add-line:horizontal,
QListWidget#thumbnailGrid QScrollBar::sub-line:horizontal,
QListWidget#selectedPhotosList QScrollBar::add-line:horizontal,
QListWidget#selectedPhotosList QScrollBar::sub-line:horizontal {
    background: transparent;
    width: 0px;
}
QListWidget#thumbnailGrid QScrollBar::add-page:horizontal,
QListWidget#thumbnailGrid QScrollBar::sub-page:horizontal,
QListWidget#selectedPhotosList QScrollBar::add-page:horizontal,
QListWidget#selectedPhotosList QScrollBar::sub-page:horizontal {
    background: transparent;
}
QLabel#browserHint {
    color: #617084;
    background: #f5f8fb;
    border: 1px dashed #ccd7e2;
    border-radius: 12px;
    padding: 12px 14px;
}
QLabel#statusCard {
    border-radius: 14px;
    padding: 14px 16px;
    font-weight: 600;
    border: 1px solid #d6e1ec;
    background: #edf4fb;
    color: #21476b;
}
QLabel#statusCard[tone="success"] {
    background: #edf8f1;
    color: #1d6a3d;
    border-color: #cfe9d8;
}
QLabel#statusCard[tone="error"] {
    background: #fff1f1;
    color: #9d2b2b;
    border-color: #efc8c8;
}
QLabel#statusCard[tone="info"] {
    background: #edf4fb;
    color: #21476b;
    border-color: #d6e1ec;
}
QLabel#browserHint[tone="success"] {
    color: #1f6b3a;
    background: #edf8f1;
    border: 1px solid #b9dfc6;
}
QLabel#browserHint[tone="error"] {
    color: #9b2c2c;
    background: #fdf1f1;
    border: 1px solid #efc4c4;
}
QLabel#filterLabel {
    color: #556579;
    font-weight: 600;
}
QPushButton#filterButton {
    background: #ffffff;
    color: #31445a;
    border: 1px solid #cad6e2;
    border-radius: 0px;
    padding: 6px 14px;
    font-weight: 600;
}
QPushButton#filterButton[segment="first"] {
    border-top-left-radius: 8px;
    border-bottom-left-radius: 8px;
}
QPushButton#filterButton[segment="middle"],
QPushButton#filterButton[segment="last"] {
    border-left: none;
}
QPushButton#filterButton[segment="last"] {
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
}
QPushButton#filterButton:hover {
    background: #f3f8fe;
}
QPushButton#filterButton:disabled {
    color: #a8b3bf;
    background: #f5f7f9;
}
QPushButton#filterButton:checked {
    background: #26425f;
    color: #ffffff;
    border-color: #26425f;
}
QPushButton#filterButton[filter="needs"]:checked {
    background: #d97706;
    border-color: #d97706;
}
QPushButton#filterButton:checked:disabled {
    background: #8fa1b4;
    color: #ffffff;
    border-color: #8fa1b4;
}
QPushButton#filterButton[filter="needs"]:checked:disabled {
    background: #e8b97a;
    border-color: #e8b97a;
}
QPushButton#filterButton[filter="has"]:checked:disabled {
    background: #8fb4ef;
    border-color: #8fb4ef;
}
QDialog#photoPicker {
    background: #eef3f8;
}
QFrame#pickerNav {
    background: #f6f9fc;
    border: none;
    border-bottom: 1px solid #d6dfe8;
}
QPushButton#pickerNavButton {
    padding: 0px;
    border-radius: 8px;
    font-size: 16px;
    color: #31445a;
}
QLineEdit#pickerPath[error="true"] {
    border: 1px solid #c62828;
    background: #fff5f5;
}
QTreeWidget#pickerTree {
    background: #fbfdff;
    border: none;
    border-right: 1px solid #d6dfe8;
    padding: 8px 6px;
    outline: none;
    font-size: 14px;
}
QTreeWidget#pickerTree::item {
    padding: 4px 6px;
    border-radius: 8px;
    color: #23384f;
}
QTreeWidget#pickerTree::item:hover {
    background: #e7eef6;
}
QTreeWidget#pickerTree::item:selected {
    background: #26425f;
    color: #ffffff;
    font-weight: 700;
}
QLabel#pickerSummary,
QLabel#pickerNote {
    color: #556579;
    font-size: 13px;
}
QLabel#pickerEmpty {
    color: #7a8899;
    font-size: 15px;
    background: transparent;
}
QPushButton#pickerAddButton {
    background: #26425f;
    color: #ffffff;
    border: 1px solid #26425f;
    padding: 10px 18px;
    font-weight: 700;
}
QPushButton#pickerAddButton:hover {
    background: #1d3550;
    border-color: #1d3550;
}
QPushButton#pickerAddButton:disabled {
    color: #8c9aa8;
    background: #f5f7f9;
    border-color: #d7dee5;
}
QPushButton#onlySelectedButton {
    background: #ffffff;
    color: #31445a;
    border: 1px solid #cad6e2;
    border-radius: 8px;
    padding: 6px 14px;
    font-weight: 600;
}
QPushButton#onlySelectedButton:hover {
    background: #fff3e3;
    border-color: #f0c48a;
}
QPushButton#onlySelectedButton:checked {
    background: #d97706;
    color: #ffffff;
    border-color: #d97706;
}
QPushButton#onlySelectedButton:disabled {
    color: #a8b3bf;
    background: #f5f7f9;
    border-color: #d7dee5;
}
QPushButton#filterButton[filter="has"]:checked {
    background: #1f6feb;
    border-color: #1f6feb;
}
QFrame#paneHeader {
    border: none;
    border-top-left-radius: 17px;
    border-top-right-radius: 17px;
}
QFrame#paneHeader[tone="list"] {
    background: #26425f;
}
QFrame#paneHeader[tone="change"] {
    background: #b45f06;
}
QLabel#paneHeaderTitle {
    color: #ffffff;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 2px;
}
QPushButton#headerButton {
    background: #ffffff;
    color: #17304a;
    border: none;
    border-radius: 8px;
    padding: 8px 14px;
}
QPushButton#headerButton:hover {
    background: #e3ecf6;
}
QPushButton#headerButton:pressed {
    background: #cfdcea;
}
QPushButton#headerOutlineButton {
    background: transparent;
    color: #e3ecf6;
    border: 1px solid #4a6889;
    border-radius: 8px;
    padding: 7px 12px;
}
QPushButton#headerOutlineButton:hover {
    background: #31506f;
    border-color: #7f9bb8;
}
QPushButton#headerOutlineButton:pressed {
    background: #1d3550;
}
QPushButton#headerOutlineButton:disabled {
    background: transparent;
    color: #7f95ad;
    border-color: #3d5a78;
}
QFrame#gridBox {
    background: #ffffff;
    border: 1px solid #e1e8ef;
    border-radius: 14px;
}
QFrame#selectionBar {
    background: #ffffff;
    border: none;
    border-bottom: 1px solid #e1e8ef;
    border-top-left-radius: 13px;
    border-top-right-radius: 13px;
}
QFrame#selectionBar[active="true"] {
    background: #fff3e3;
    border-bottom: 1px solid #f0c48a;
}
QLabel#selectionDot {
    color: #c3ccd6;
    font-size: 10px;
}
QFrame#selectionBar[active="true"] QLabel#selectionDot {
    color: #d97706;
}
QLabel#selectionCount {
    color: #7a8899;
    font-weight: 700;
}
QFrame#selectionBar[active="true"] QLabel#selectionCount {
    color: #7a4100;
}
QLabel#selectionBarSeparator {
    color: #d6dfe8;
}
QFrame#selectionBar[active="true"] QLabel#selectionBarSeparator {
    color: #e2b47a;
}
QPushButton#selectionBarButton {
    background: transparent;
    color: #1f5fc4;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
}
QPushButton#selectionBarButton:hover {
    background: #eef4fb;
}
QFrame#selectionBar[active="true"] QPushButton#selectionBarButton {
    color: #8a4b00;
}
QFrame#selectionBar[active="true"] QPushButton#selectionBarButton:hover {
    background: #fde4c4;
}
QPushButton#selectionBarButton:disabled,
QFrame#selectionBar[active="true"] QPushButton#selectionBarButton:disabled {
    background: transparent;
    color: #a9b4c0;
}
/* The picker's "Add Photos in Subfolders" (shown while a folder is selected). */
QCheckBox#selectionBarCheck {
    background: #ffffff;
    color: #7a4100;
    font-weight: 700;
    border: 1px solid #f0c48a;
    border-radius: 8px;
    padding: 5px 10px;
    spacing: 7px;
}
QCheckBox#selectionBarCheck:hover {
    background: #fff8ee;
}
QLabel#fieldLabel {
    color: #31445a;
    font-size: 13px;
    font-weight: 600;
}
QTabWidget#editorTabs::pane {
    background: transparent;
    border: none;
    border-top: 1px solid #e1e8ef;
    top: -1px;
}
QTabWidget#editorTabs::tab-bar {
    left: 20px;
}
QTabWidget#editorTabs QTabBar::tab {
    background: transparent;
    color: #556579;
    border: none;
    border-bottom: 3px solid transparent;
    padding: 9px 14px 9px 14px;
    margin-right: 4px;
    font-size: 15px;
    font-weight: 600;
}
QTabWidget#editorTabs QTabBar::tab:hover {
    color: #17304a;
}
/* The tab shown is the mode the app is in: orange, like the selection. */
QTabWidget#editorTabs QTabBar::tab:selected {
    background: #d97706;
    color: #ffffff;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}
QFrame#tabPlaceholder {
    background: #f5f8fb;
    border: 2px dashed #ccd7e2;
    border-radius: 14px;
}
QLabel#tabPlaceholderTitle {
    color: #31445a;
    font-size: 16px;
    font-weight: 700;
}
QLabel#tabPlaceholderDetail {
    color: #556579;
}
QGroupBox#locationGroup {
    background: #f4f8ff;
    border: 1px solid #b9d0f5;
}
QGroupBox#locationGroup::title {
    color: #1f5fc4;
}
QScrollArea#dateScroll,
QWidget#dateScrollContent {
    background: transparent;
}
/* Date & Time steps: orange = the step to do now, navy ✓ = done, grey = later. */
QFrame#stepBox {
    border: 1px solid #e1e8ef;
    border-radius: 12px;
    background: #ffffff;
}
QFrame#stepBox[state="active"] {
    border-color: #f0c48a;
    background: #fffaf3;
}
QFrame#stepBox[state="locked"] {
    background: #f7f9fb;
}
QLabel#stepCircle {
    border-radius: 14px;
    font-weight: 700;
    font-size: 14px;
    background: #26425f;
    color: #ffffff;
}
QFrame#stepBox[state="active"] QLabel#stepCircle {
    background: #d97706;
}
QFrame#stepBox[state="locked"] QLabel#stepCircle {
    background: #e3e9f0;
    color: #8c9aa8;
}
QLabel#stepTitle {
    font-weight: 700;
    font-size: 15px;
    color: #162131;
}
QFrame#stepBox[state="locked"] QLabel#stepTitle {
    color: #8c9aa8;
}
QLabel#stepSummary {
    color: #556579;
    font-size: 13px;
}
QFrame#stepBox[state="locked"] QLabel#stepSummary {
    color: #8c9aa8;
}
QLabel#stepHint {
    color: #7a4100;
    font-size: 13px;
}
/* Step 1's Add Photos when the list is empty (blue). */
QPushButton#stepAddButton {
    background: #1f6feb;
    color: #ffffff;
    border: 1px solid #1f6feb;
    border-radius: 8px;
    padding: 7px 14px;
    font-weight: 600;
}
QPushButton#stepAddButton:hover {
    background: #1a5fd0;
}
QPushButton#choiceCard {
    background: #ffffff;
    border: 2px solid #e1e8ef;
    border-radius: 10px;
    text-align: left;
}
QPushButton#choiceCard:hover {
    border-color: #f0c48a;
}
QPushButton#choiceCard:checked {
    background: #fff3e3;
    border-color: #d97706;
}
QLabel#choiceTitle {
    font-weight: 700;
    font-size: 16px;
    color: #162131;
}
QLabel#choiceDetail {
    font-size: 13px;
    color: #556579;
}
QDateEdit#dateField,
QComboBox#timeField {
    background: #ffffff;
    color: #162131;
    border: 1px solid #cad6e2;
    border-radius: 8px;
    font-size: 16px;
    min-height: 30px;
}
QDateEdit#dateField {
    padding: 2px 8px;
    min-width: 132px;
}
QComboBox#timeField {
    padding: 2px 4px 2px 10px;
    min-width: 30px;
}
/* Qt's own arrows are replaced by one drawn in code (date_time_picker.py). */
QComboBox#timeField::drop-down,
QComboBox#timeZoneCombo::drop-down,
QDateEdit#dateField::drop-down {
    width: 22px;
    border: none;
}
QComboBox#timeField::down-arrow,
QComboBox#timeZoneCombo::down-arrow,
QDateEdit#dateField::down-arrow {
    image: none;
    width: 0px;
    height: 0px;
}
QDateEdit#dateField:focus,
QComboBox#timeField:focus {
    border-color: #1f6feb;
}
QComboBox#timeZoneCombo {
    background: #ffffff;
    color: #162131;
    border: 1px solid #cad6e2;
    border-radius: 8px;
    font-size: 14px;
    padding: 6px 10px;
    min-height: 22px;
}
/* The photos have more than one time zone: choosing one changes them all. */
QComboBox#timeZoneCombo[mixed="true"] {
    color: #c62828;
    border-color: #e8a0a0;
    background: #fff5f5;
}
QLabel#timeColon,
QLabel#amPmLabel {
    color: #31445a;
    font-size: 16px;
}
QLabel#timeColon {
    font-weight: 700;
}
QPushButton#referenceArrow {
    background: #ffffff;
    color: #1f5fc4;
    border: 1px solid #b9d0f5;
    border-radius: 6px;
    padding: 0px;
    font-size: 16px;
}
QPushButton#referenceArrow:hover {
    background: #eaf2fe;
}
QPushButton#referenceArrow:disabled {
    color: #a8b3bf;
    border-color: #dde5ee;
}
QTreeWidget#dateChangesList {
    background: #ffffff;
    border: 1px solid #f0d9b8;
    border-radius: 8px;
    font-size: 13px;
    outline: none;
}
QTreeWidget#dateChangesList::item {
    padding: 3px 2px;
    border-bottom: 1px solid #f6ead8;
}
/* Camera groups in the Photo List (Date & Time mode): navy, the list's color. */
QLabel#thumbnailGroupHeader[group="camera"],
QLabel#groupDot[group="camera"] {
    color: #26425f;
}
QPushButton#pickButton {
    background: #ffffff;
    color: #1f5fc4;
    border: 1px solid #8cb7f0;
}
QPushButton#pickButton:hover {
    background: #e8f1ff;
}
QPushButton#pickButton:checked {
    background: #1f6feb;
    color: #ffffff;
    border-color: #1f6feb;
}
QFrame#pickBanner {
    background: #1f6feb;
    border-radius: 10px;
}
QLabel#pickBannerText {
    color: #ffffff;
    font-weight: 600;
}
QPushButton#pickCancel {
    background: #ffffff;
    color: #1f5fc4;
    border: none;
    padding: 6px 14px;
}
QLabel#mapHint {
    color: #556579;
}
QLabel#mapReadout {
    color: #31445a;
    font-weight: 600;
}
QFrame#mapProblem {
    background: #fff7e6;
    border: 1px solid #f0c27a;
    border-radius: 8px;
}
QLabel#mapProblemText {
    color: #7a4a00;
}
QPushButton#previewThumb {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 0px;
}
QPushButton#previewThumb:hover {
    background: #e8f1ff;
    border-color: #8cb7f0;
}
QPushButton#previewStep {
    background: transparent;
    border: none;
    color: #1f5fc4;
    font-size: 16px;
    font-weight: 700;
    padding: 0px 6px;
    min-width: 0px;
}
QPushButton#previewStep:hover {
    color: #17428a;
    background: #e8f1ff;
    border-radius: 4px;
}
QLabel#previewCount {
    color: #31445a;
}
QLabel#settingsHelp {
    color: #556579;
}
QLabel#mapAttribution {
    background: rgba(255, 255, 255, 210);
    color: #31445a;
    font-size: 11px;
    padding: 2px 6px;
}
QFrame#mapPreview {
    background: #ffffff;
    border: 1px solid #cad6e2;
    border-radius: 8px;
}
QLabel#mapPreviewName {
    color: #102033;
    font-weight: 600;
}
QFrame#sourceCard {
    background: #e3eeff;
    border: 1px solid #8cb7f0;
    border-radius: 10px;
}
QLabel#sourceCardTitle {
    color: #17428a;
    font-weight: 700;
}
QLabel#sourceCardDetail {
    color: #31445a;
    font-size: 12px;
}
QPushButton#sourceCardClear {
    background: transparent;
    border: none;
    color: #31445a;
    padding: 0px;
    font-weight: 700;
}
QPushButton#sourceCardClear:hover {
    background: #cfe0fb;
    border-radius: 15px;
}
QLabel#selectionGps {
    color: #31445a;
    font-size: 13px;
}
QLabel#applyHint {
    font-size: 12px;
    padding: 2px 2px;
}
QLabel#applyHint[tone="info"] {
    color: #617084;
}
QLabel#applyHint[tone="warning"] {
    color: #8a5300;
}
QLabel#applyHint[tone="error"] {
    color: #9b2c2c;
}
QPushButton#removeGpsButton {
    background: #ffffff;
    color: #b42f2f;
    border: 1px solid #e3b3b3;
    padding: 8px 14px;
}
QPushButton#removeGpsButton:hover {
    background: #fdf1f1;
    border-color: #c24141;
}
QPushButton#removeGpsButton:pressed {
    background: #f9e2e2;
}
QPushButton#removeGpsButton:disabled {
    color: #8c9aa8;
    background: #f5f7f9;
    border-color: #d7dee5;
}
QLabel#loadingText {
    color: #556579;
    font-size: 12px;
}
QProgressBar#loadingBar {
    background: #e3e9f0;
    border: none;
    border-radius: 3px;
}
QProgressBar#loadingBar::chunk {
    background: #d97706;
    border-radius: 3px;
}
QPushButton#loadingCancel {
    padding: 4px 12px;
}
QSplitter::handle {
    background: transparent;
    width: 10px;
}
"""
