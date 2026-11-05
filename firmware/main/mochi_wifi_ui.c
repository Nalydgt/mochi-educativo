#include "mochi_fonts.h"
#include "mochi_wifi_ui.h"

#include "mochi.h"
#include "mochi_runtime.h"
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

/* The rectangular keyboard fits inside the round panel, including its corners. */
#define TEXT 0xF3F1F7
#define MUTED 0xAEB1BE
#define SURFACE 0x232631
#define ACCENT 0xE7ABC8
#define KEY(width) (LV_BUTTONMATRIX_CTRL_CLICK_TRIG | LV_BUTTONMATRIX_CTRL_NO_REPEAT | (width))

typedef enum { PAGE_LIST, PAGE_SSID, PAGE_PASSWORD, PAGE_OPEN } wifi_page_t;
static lv_obj_t *overlay, *list_page, *editor_page, *networks_list;
static lv_obj_t *connection_label, *list_note, *scan_button, *manual_button;
static lv_obj_t *editor_title, *editor_caption, *editor_input, *editor_note;
static lv_obj_t *show_button, *show_label, *open_button, *open_label;
static lv_obj_t *keyboard, *submit_button, *submit_label;
static wifi_page_t page;
static mochi_wifi_status_t snapshot;
static atomic_bool opened;
static bool preview, manual_open, password_visible;
static char selected_ssid[33];
static uint32_t shown_revision;

static void render_list(void);
static void show_list(void);
static void show_editor(wifi_page_t next);
static void submit_editor(void);

/* The alternate symbol page makes every printable ASCII password character
 * reachable without asking a phone or PC to supply the password. */
static const char *const lower_map[] = {
    "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "\n",
    "a", "s", "d", "f", "g", "h", "j", "k", "l", "\n",
    "ABC", "z", "x", "c", "v", "b", "n", "m", ".", "\n",
    "1#", "espacio", LV_SYMBOL_BACKSPACE, LV_SYMBOL_OK, ""
};
static const char *const upper_map[] = {
    "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "\n",
    "A", "S", "D", "F", "G", "H", "J", "K", "L", "\n",
    "abc", "Z", "X", "C", "V", "B", "N", "M", ".", "\n",
    "1#", "espacio", LV_SYMBOL_BACKSPACE, LV_SYMBOL_OK, ""
};
static const lv_buttonmatrix_ctrl_t letter_controls[] = {
    KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1),
    KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1),
    KEY(2), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1),
    KEY(2), KEY(4), KEY(2), KEY(2)
};
static const char *const symbol_map[] = {
    "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "\n",
    "!", "@", "#", "$", "%", "^", "&", "*", "(", ")", "\n",
    "-", "_", "+", "=", "[", "]", "{", "}", ":", ";", "\n",
    "abc", "#+", "espacio", LV_SYMBOL_BACKSPACE, LV_SYMBOL_OK, ""
};
static const char *const extra_map[] = {
    "`", "~", "|", "\\", "/", "?", "<", ">", "\"", "'", "\n",
    ".", ",", ":", ";", "=", "+", "-", "_", "[", "]", "\n",
    "{", "}", "!", "@", "#", "$", "%", "^", "&", "*", "\n",
    "abc", "1#", "espacio", LV_SYMBOL_BACKSPACE, LV_SYMBOL_OK, ""
};
static const lv_buttonmatrix_ctrl_t symbol_controls[] = {
    KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1),
    KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1),
    KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1), KEY(1),
    KEY(2), KEY(2), KEY(4), KEY(2), KEY(2)
};

static void plain_container(lv_obj_t *obj, int x, int y, int w, int h)
{
    lv_obj_remove_style_all(obj);
    lv_obj_set_pos(obj, x, y);
    lv_obj_set_size(obj, w, h);
    lv_obj_set_style_bg_color(obj, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
    lv_obj_set_style_text_color(obj, lv_color_hex(TEXT), 0);
    lv_obj_set_style_text_font(obj, &mochi_font_16, 0);
    lv_obj_remove_flag(obj, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_GESTURE_BUBBLE | LV_OBJ_FLAG_EVENT_BUBBLE);
}

static lv_obj_t *label_at(lv_obj_t *parent, const char *text, int x, int y, int w,
                          const lv_font_t *font, uint32_t color)
{
    lv_obj_t *label = lv_label_create(parent);
    lv_obj_set_pos(label, x, y);
    lv_obj_set_width(label, w);
    lv_label_set_text(label, text);
    lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_color(label, lv_color_hex(color), 0);
    lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
    return label;
}

static lv_obj_t *button_at(lv_obj_t *parent, const char *text, int x, int y,
                           int w, int h, lv_event_cb_t callback, void *data)
{
    lv_obj_t *button = lv_button_create(parent);
    lv_obj_set_pos(button, x, y);
    lv_obj_set_size(button, w, h);
    lv_obj_set_style_bg_color(button, lv_color_hex(SURFACE), 0);
    lv_obj_set_style_bg_color(button, lv_color_hex(0x3F3440), LV_STATE_PRESSED);
    lv_obj_set_style_bg_opa(button, LV_OPA_50, LV_STATE_DISABLED);
    lv_obj_set_style_radius(button, 14, 0);
    lv_obj_set_style_shadow_width(button, 0, 0);
    lv_obj_set_style_border_width(button, 0, 0);
    lv_obj_set_style_pad_all(button, 0, 0);
    lv_obj_set_style_text_font(button, &mochi_font_16, 0);
    lv_obj_set_style_text_color(button, lv_color_hex(TEXT), 0);
    lv_obj_remove_flag(button, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_GESTURE_BUBBLE | LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_t *label = lv_label_create(button);
    lv_label_set_text(label, text);
    lv_obj_center(label);
    if (callback) lv_obj_add_event_cb(button, callback, LV_EVENT_CLICKED, data);
    return button;
}

static void set_enabled(lv_obj_t *obj, bool enabled)
{
    if (enabled) lv_obj_remove_state(obj, LV_STATE_DISABLED);
    else lv_obj_add_state(obj, LV_STATE_DISABLED);
}

static const char *error_text(mochi_wifi_error_t error)
{
    switch (error) {
    case MOCHI_WIFI_ERROR_BUSY: return "Espera a que Mochi termine";
    case MOCHI_WIFI_ERROR_INVALID: return "Revisa el nombre y la clave";
    case MOCHI_WIFI_ERROR_UNAVAILABLE: return "Wi-Fi no disponible. Reintenta";
    case MOCHI_WIFI_ERROR_SCAN: return "No pude buscar. Pulsa Buscar";
    case MOCHI_WIFI_ERROR_AUTH: return "No se pudo entrar. Revisa la clave";
    case MOCHI_WIFI_ERROR_TIMEOUT: return "No responde. Acerca Mochi a la red";
    case MOCHI_WIFI_ERROR_SAVE: return "No pude guardar. Vuelve a intentarlo";
    case MOCHI_WIFI_ERROR_CONNECT: return "No pude conectar. Vuelve a intentarlo";
    default: return "Elige una red de 2,4 GHz";
    }
}

static void clear_input(void)
{
    password_visible = false;
    if (editor_input) {
        /* This textarea always owns its nonempty text. Erase the active copy
         * before LVGL releases it; this does not promise heap sanitization of
         * older reallocations made internally while editing. */
        const char *active = lv_textarea_get_text(editor_input);
        size_t length = strlen(active);
        volatile char *wipe = (volatile char *)active;
        while (length) wipe[--length] = 0;
        lv_textarea_set_text(editor_input, "");
        lv_textarea_set_password_mode(editor_input, true);
    }
    if (show_label) lv_label_set_text(show_label, "Ver");
}

static void back_event(lv_event_t *event)
{
    (void)event;
    if (page == PAGE_LIST) mochi_wifi_ui_close();
    else {
        clear_input();
        show_list();
    }
}

static void scan_event(lv_event_t *event)
{
    (void)event;
    preview = false;
    if (!mochi_wifi_scan_start()) {
        lv_label_set_text(list_note, "Espera a que Mochi termine");
        return;
    }
    mochi_wifi_get_status(&snapshot);
    render_list();
}

static void manual_event(lv_event_t *event)
{
    (void)event;
    selected_ssid[0] = '\0';
    manual_open = false;
    show_editor(PAGE_SSID);
}

static void network_event(lv_event_t *event)
{
    size_t index = (size_t)lv_event_get_user_data(event);
    if (index >= snapshot.count || index >= MOCHI_WIFI_MAX_NETWORKS) return;
    const mochi_wifi_network_t *network = &snapshot.networks[index];
    snprintf(selected_ssid, sizeof(selected_ssid), "%s", network->ssid);
    if (network->current && snapshot.connected) {
        lv_label_set_text(list_note, "Ya estas conectado a esta red");
        return;
    }
    show_editor(network->secured ? PAGE_PASSWORD : PAGE_OPEN);
}

static void render_list(void)
{
    shown_revision = snapshot.revision;
    bool busy = snapshot.phase == MOCHI_WIFI_SCANNING || snapshot.phase == MOCHI_WIFI_CONNECTING;
    set_enabled(scan_button, !busy);
    set_enabled(manual_button, !busy);
    if (snapshot.phase == MOCHI_WIFI_CONNECTING) {
        lv_label_set_text(connection_label, "Conectando...");
        lv_label_set_text(list_note, "Puede tardar unos segundos");
    } else if (snapshot.phase == MOCHI_WIFI_SCANNING) {
        lv_label_set_text(connection_label, snapshot.connected ? "Conectado - buscando redes" : "Buscando redes...");
        lv_label_set_text(list_note, "Solo aparecen redes de 2,4 GHz");
    } else {
        if (snapshot.connected && snapshot.current_ssid[0])
            lv_label_set_text_fmt(connection_label, "Conectado a %s", snapshot.current_ssid);
        else lv_label_set_text(connection_label, "Sin conexion Wi-Fi");
        if (snapshot.phase == MOCHI_WIFI_FAILED) lv_label_set_text(list_note, error_text(snapshot.error));
        else lv_label_set_text(list_note, snapshot.count ? "Elige una red de 2,4 GHz" : "Pulsa Buscar o escribe otra red");
    }
    lv_obj_clean(networks_list);
    for (size_t i = 0; i < snapshot.count && i < MOCHI_WIFI_MAX_NETWORKS; ++i) {
        const mochi_wifi_network_t *network = &snapshot.networks[i];
        lv_obj_t *row = button_at(networks_list, "", 0, (int)i * 59, 298, 53,
                                  network_event, (void *)i);
        set_enabled(row, !busy);
        lv_obj_set_style_bg_color(row, lv_color_hex(network->current ? 0x352A35 : SURFACE), 0);
        lv_obj_t *name = label_at(row, network->ssid, 14, 8, 227, &mochi_font_16, TEXT);
        lv_obj_set_style_text_align(name, LV_TEXT_ALIGN_LEFT, 0);
        lv_label_set_long_mode(name, LV_LABEL_LONG_MODE_DOTS);
        const char *strength = network->rssi >= -60 ? "Buena" : network->rssi >= -75 ? "Media" : "Debil";
        char detail[48];
        snprintf(detail, sizeof(detail), "%s / %s", network->current ? "Actual" : network->secured ? "Con clave" : "Sin clave", strength);
        lv_obj_t *sub = label_at(row, detail, 14, 30, 242, &mochi_font_14, MUTED);
        lv_obj_set_style_text_align(sub, LV_TEXT_ALIGN_LEFT, 0);
        label_at(row, network->current ? LV_SYMBOL_OK : LV_SYMBOL_RIGHT, 264, 18, 20, &mochi_font_14,
                 network->current ? ACCENT : MUTED);
    }
    if (!snapshot.count) {
        label_at(networks_list, snapshot.phase == MOCHI_WIFI_SCANNING ? "Buscando cerca de ti..." : "Aun no hay redes en la lista",
                 10, 55, 278, &mochi_font_16, MUTED);
    }
}

static void show_list(void)
{
    page = PAGE_LIST;
    lv_obj_add_flag(editor_page, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(list_page, LV_OBJ_FLAG_HIDDEN);
    if (!preview) mochi_wifi_get_status(&snapshot);
    render_list();
}

static void show_password_event(lv_event_t *event)
{
    (void)event;
    password_visible = !password_visible;
    lv_textarea_set_password_mode(editor_input, !password_visible);
    lv_label_set_text(show_label, password_visible ? "Ocultar" : "Ver");
    lv_obj_set_style_text_font(show_label, &mochi_font_14, 0);
}

static void toggle_open_event(lv_event_t *event)
{
    (void)event;
    manual_open = !manual_open;
    lv_label_set_text(open_label, manual_open ? "Sin clave: si" : "Sin clave: no");
    lv_obj_set_style_bg_color(open_button, lv_color_hex(manual_open ? 0x47303D : SURFACE), 0);
}

static void keyboard_event(lv_event_t *event)
{
    if (lv_event_get_code(event) == LV_EVENT_READY) {
        submit_editor();
        return;
    }
    uint32_t id = lv_keyboard_get_selected_button(keyboard);
    if (id == LV_BUTTONMATRIX_BUTTON_NONE) return;
    const char *text = lv_keyboard_get_button_text(keyboard, id);
    if (!text) return;
    if (!strcmp(text, "#+")) lv_keyboard_set_mode(keyboard, LV_KEYBOARD_MODE_USER_1);
    else if (!strcmp(text, "espacio")) lv_textarea_add_text(editor_input, " ");
    else lv_keyboard_def_event_cb(event);
}

static void submit_event(lv_event_t *event)
{
    (void)event;
    submit_editor();
}

static bool valid_password(const char *text)
{
    size_t length = strlen(text);
    if (length >= 8 && length <= 63) return true;
    if (length != 64) return false;
    for (size_t i = 0; i < length; ++i) {
        char c = text[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) return false;
    }
    return true;
}

static void submit_editor(void)
{
    if (page == PAGE_SSID) {
        const char *name = lv_textarea_get_text(editor_input);
        size_t length = strlen(name);
        if (!length || length > 32) {
            lv_label_set_text(editor_caption, "Nombre de 1 a 32 bytes");
            lv_obj_set_style_text_color(editor_caption, lv_color_hex(ACCENT), 0);
            return;
        }
        memcpy(selected_ssid, name, length + 1);
        show_editor(manual_open ? PAGE_OPEN : PAGE_PASSWORD);
        return;
    }
    if (page != PAGE_PASSWORD && page != PAGE_OPEN) return;
    const char *password = page == PAGE_OPEN ? "" : lv_textarea_get_text(editor_input);
    if (page == PAGE_PASSWORD && !valid_password(password)) {
        lv_label_set_text(editor_note, "Usa de 8 a 63 caracteres\no 64 digitos hexadecimales");
        lv_obj_set_style_text_color(editor_note, lv_color_hex(ACCENT), 0);
        return;
    }
    if (preview) {
        lv_label_set_text(editor_note, "Vista previa: no se cambia la red");
        return;
    }
    if (!mochi_wifi_connect_start(selected_ssid, password)) {
        lv_label_set_text(editor_note, "Espera a que Mochi termine\ny vuelve a pulsar Conectar");
        lv_obj_set_style_text_color(editor_note, lv_color_hex(ACCENT), 0);
        return;
    }
    clear_input();
    show_list();
}

static void show_editor(wifi_page_t next)
{
    clear_input();
    page = next;
    lv_obj_add_flag(list_page, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(editor_page, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_text_color(editor_caption, lv_color_hex(MUTED), 0);
    lv_obj_set_style_text_color(editor_note, lv_color_hex(MUTED), 0);
    lv_obj_add_flag(open_button, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(show_button, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(editor_input, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(keyboard, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(editor_note, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_pos(submit_button, 158, 405);
    lv_obj_set_size(submit_button, 150, 40);
    lv_obj_set_pos(editor_note, 83, 178);
    lv_obj_set_width(editor_note, 300);
    lv_obj_set_width(editor_input, next == PAGE_PASSWORD ? 224 : 300);
    lv_textarea_set_password_mode(editor_input, next == PAGE_PASSWORD);
    lv_textarea_set_max_length(editor_input, next == PAGE_SSID ? 32 : 64);
    lv_textarea_set_accepted_chars(editor_input, next == PAGE_PASSWORD ?
        " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~" : NULL);
    lv_keyboard_set_mode(keyboard, LV_KEYBOARD_MODE_TEXT_LOWER);
    lv_keyboard_set_textarea(keyboard, editor_input);
    if (next == PAGE_SSID) {
        lv_label_set_text(editor_title, "Nombre de red");
        lv_label_set_text(editor_caption, "Red oculta o nombre manual");
        lv_textarea_set_placeholder_text(editor_input, "Nombre exacto (SSID)");
        lv_label_set_text(submit_label, "Continuar");
        lv_obj_add_flag(editor_note, LV_OBJ_FLAG_HIDDEN);
        lv_obj_remove_flag(open_button, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(open_label, manual_open ? "Sin clave: si" : "Sin clave: no");
        lv_obj_set_style_bg_color(open_button, lv_color_hex(manual_open ? 0x47303D : SURFACE), 0);
    } else {
        lv_label_set_text(editor_title, next == PAGE_OPEN ? "Conectar" : "Contrasena");
        lv_label_set_text(editor_caption, selected_ssid);
        lv_label_set_text(submit_label, "Conectar");
        if (next == PAGE_PASSWORD) {
            lv_textarea_set_placeholder_text(editor_input, "Clave de la red");
            lv_label_set_text(editor_note, "8-63 caracteres o 64 en hexadecimal");
            lv_obj_remove_flag(show_button, LV_OBJ_FLAG_HIDDEN);
        } else {
            lv_obj_add_flag(editor_input, LV_OBJ_FLAG_HIDDEN);
            lv_obj_add_flag(keyboard, LV_OBJ_FLAG_HIDDEN);
            lv_obj_set_pos(editor_note, 93, 185);
            lv_obj_set_width(editor_note, 280);
            lv_label_set_text(editor_note, "Esta red no tiene contrasena.\n\nPulsa Conectar para usarla.");
            lv_obj_set_pos(submit_button, 139, 294);
            lv_obj_set_size(submit_button, 188, 48);
        }
    }
}

static void poll_status(lv_timer_t *timer)
{
    (void)timer;
    if (!opened || preview || page != PAGE_LIST) return;
    mochi_wifi_status_t latest;
    mochi_wifi_get_status(&latest);
    if (latest.revision == shown_revision) return;
    snapshot = latest;
    render_list();
}

void mochi_wifi_ui_create(lv_obj_t *screen)
{
    if (overlay) return;
    overlay = lv_obj_create(screen);
    plain_container(overlay, 0, 0, 466, 466);
    list_page = lv_obj_create(overlay);
    plain_container(list_page, 0, 0, 466, 466);
    editor_page = lv_obj_create(overlay);
    plain_container(editor_page, 0, 0, 466, 466);

    button_at(list_page, LV_SYMBOL_LEFT, 87, 54, 46, 42, back_event, NULL);
    label_at(list_page, "Wi-Fi", 147, 65, 172, &mochi_font_20, TEXT);
    connection_label = label_at(list_page, "", 83, 112, 300, &mochi_font_16, TEXT);
    lv_obj_set_height(connection_label, 40);
    lv_label_set_long_mode(connection_label, LV_LABEL_LONG_MODE_DOTS);
    networks_list = lv_obj_create(list_page);
    plain_container(networks_list, 78, 164, 310, 172);
    lv_obj_add_flag(networks_list, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scroll_dir(networks_list, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(networks_list, LV_SCROLLBAR_MODE_AUTO);
    lv_obj_set_style_width(networks_list, 3, LV_PART_SCROLLBAR);
    lv_obj_set_style_bg_color(networks_list, lv_color_hex(ACCENT), LV_PART_SCROLLBAR);
    scan_button = button_at(list_page, LV_SYMBOL_REFRESH "  Buscar", 87, 349, 140, 44, scan_event, NULL);
    manual_button = button_at(list_page, "Otra red", 239, 349, 140, 44, manual_event, NULL);
    list_note = label_at(list_page, "", 133, 402, 200, &mochi_font_14, MUTED);
    lv_obj_set_height(list_note, 36);

    button_at(editor_page, LV_SYMBOL_LEFT, 87, 54, 46, 42, back_event, NULL);
    editor_title = label_at(editor_page, "", 137, 65, 215, &mochi_font_20, TEXT);
    editor_caption = label_at(editor_page, "", 83, 100, 300, &mochi_font_14, MUTED);
    lv_label_set_long_mode(editor_caption, LV_LABEL_LONG_MODE_DOTS);
    editor_input = lv_textarea_create(editor_page);
    lv_obj_set_pos(editor_input, 83, 127);
    lv_obj_set_size(editor_input, 300, 44);
    lv_textarea_set_one_line(editor_input, true);
    lv_textarea_set_password_bullet(editor_input, "*");
    lv_textarea_set_password_show_time(editor_input, 0);
    lv_obj_set_style_bg_color(editor_input, lv_color_hex(SURFACE), 0);
    lv_obj_set_style_border_color(editor_input, lv_color_hex(ACCENT), 0);
    lv_obj_set_style_border_width(editor_input, 1, 0);
    lv_obj_set_style_radius(editor_input, 12, 0);
    lv_obj_set_style_text_color(editor_input, lv_color_hex(TEXT), 0);
    lv_obj_set_style_text_color(editor_input, lv_color_hex(ACCENT), LV_PART_CURSOR);
    lv_obj_set_style_pad_left(editor_input, 12, 0);
    lv_obj_set_style_pad_right(editor_input, 12, 0);
    lv_obj_set_style_pad_top(editor_input, 12, 0);
    lv_obj_set_style_text_font(editor_input, &mochi_font_16, 0);
    lv_obj_remove_flag(editor_input, LV_OBJ_FLAG_GESTURE_BUBBLE | LV_OBJ_FLAG_EVENT_BUBBLE);
    show_button = button_at(editor_page, "Ver", 315, 127, 68, 44, show_password_event, NULL);
    show_label = lv_obj_get_child(show_button, 0);
    editor_note = label_at(editor_page, "", 83, 178, 300, &mochi_font_14, MUTED);
    open_button = button_at(editor_page, "Sin clave: no", 148, 178, 170, 34, toggle_open_event, NULL);
    open_label = lv_obj_get_child(open_button, 0);
    lv_obj_set_style_text_font(open_button, &mochi_font_14, 0);

    keyboard = lv_keyboard_create(editor_page);
    /* The widget constructor anchors keyboards to BOTTOM_MID. Absolute
     * coordinates below must use TOP_LEFT, otherwise y=222 is off-panel. */
    lv_obj_set_align(keyboard, LV_ALIGN_TOP_LEFT);
    lv_obj_set_pos(keyboard, 73, 222);
    lv_obj_set_size(keyboard, 320, 174);
    lv_keyboard_set_map(keyboard, LV_KEYBOARD_MODE_TEXT_LOWER, lower_map, letter_controls);
    lv_keyboard_set_map(keyboard, LV_KEYBOARD_MODE_TEXT_UPPER, upper_map, letter_controls);
    lv_keyboard_set_map(keyboard, LV_KEYBOARD_MODE_SPECIAL, symbol_map, symbol_controls);
    lv_keyboard_set_map(keyboard, LV_KEYBOARD_MODE_USER_1, extra_map, symbol_controls);
    lv_keyboard_set_popovers(keyboard, false);
    lv_obj_set_style_bg_opa(keyboard, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(keyboard, 0, 0);
    lv_obj_set_style_pad_all(keyboard, 0, 0);
    lv_obj_set_style_pad_row(keyboard, 5, 0);
    lv_obj_set_style_pad_column(keyboard, 3, 0);
    lv_obj_set_style_bg_color(keyboard, lv_color_hex(SURFACE), LV_PART_ITEMS);
    lv_obj_set_style_bg_color(keyboard, lv_color_hex(0x624154), LV_PART_ITEMS | LV_STATE_PRESSED);
    lv_obj_set_style_bg_opa(keyboard, LV_OPA_COVER, LV_PART_ITEMS);
    lv_obj_set_style_text_color(keyboard, lv_color_hex(TEXT), LV_PART_ITEMS);
    lv_obj_set_style_text_font(keyboard, &mochi_font_14, LV_PART_ITEMS);
    lv_obj_set_style_radius(keyboard, 8, LV_PART_ITEMS);
    lv_obj_set_style_border_width(keyboard, 0, LV_PART_ITEMS);
    lv_obj_set_style_shadow_width(keyboard, 0, LV_PART_ITEMS);
    lv_obj_remove_flag(keyboard, LV_OBJ_FLAG_GESTURE_BUBBLE | LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_remove_event_cb(keyboard, lv_keyboard_def_event_cb);
    lv_obj_add_event_cb(keyboard, keyboard_event, LV_EVENT_VALUE_CHANGED, NULL);
    lv_obj_add_event_cb(keyboard, keyboard_event, LV_EVENT_READY, NULL);
    submit_button = button_at(editor_page, "Conectar", 158, 405, 150, 40, submit_event, NULL);
    submit_label = lv_obj_get_child(submit_button, 0);
    lv_obj_set_style_bg_color(submit_button, lv_color_hex(ACCENT), 0);
    lv_obj_set_style_text_color(submit_button, lv_color_hex(0x201820), 0);
    lv_obj_add_flag(overlay, LV_OBJ_FLAG_HIDDEN);
    lv_timer_create(poll_status, 250, NULL);
}

void mochi_wifi_ui_open(void)
{
    if (!overlay) return;
    preview = false;
    opened = true;
    clear_input();
    mochi_settings_set_open(true);
    lv_obj_remove_flag(overlay, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(overlay);
    show_list();
    if (snapshot.phase != MOCHI_WIFI_SCANNING && snapshot.phase != MOCHI_WIFI_CONNECTING) {
        bool scanning = mochi_wifi_scan_start();
        mochi_wifi_get_status(&snapshot);
        render_list();
        if (!scanning) lv_label_set_text(list_note, "Espera a que Mochi termine");
    }
}

void mochi_wifi_ui_close(void)
{
    if (!overlay) return;
    opened = false;
    preview = false;
    clear_input();
    selected_ssid[0] = '\0';
    lv_obj_add_flag(overlay, LV_OBJ_FLAG_HIDDEN);
}

bool mochi_wifi_ui_is_open(void) { return atomic_load_explicit(&opened, memory_order_acquire); }

void mochi_wifi_ui_preview(const char *name)
{
    if (!overlay) return;
    opened = preview = true;
    mochi_settings_set_open(true);
    lv_obj_remove_flag(overlay, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(overlay);
    memset(&snapshot, 0, sizeof(snapshot));
    snapshot.phase = MOCHI_WIFI_CONNECTED;
    snapshot.connected = true;
    snapshot.count = 3;
    snprintf(snapshot.current_ssid, sizeof(snapshot.current_ssid), "Casa");
    snapshot.networks[0] = (mochi_wifi_network_t){ .ssid = "Casa", .rssi = -48, .secured = true, .current = true };
    snapshot.networks[1] = (mochi_wifi_network_t){ .ssid = "Mi iPhone", .rssi = -59, .secured = true };
    snapshot.networks[2] = (mochi_wifi_network_t){ .ssid = "Red de invitados", .rssi = -72, .secured = false };
    snprintf(selected_ssid, sizeof(selected_ssid), "Mi iPhone");
    manual_open = false;
    if (name && !strcmp(name, "ssid")) show_editor(PAGE_SSID);
    else if (name && !strcmp(name, "password")) show_editor(PAGE_PASSWORD);
    else if (name && !strcmp(name, "open")) show_editor(PAGE_OPEN);
    else show_list();
}
