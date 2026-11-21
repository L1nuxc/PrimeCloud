#![windows_subsystem = "windows"]
extern crate native_windows_gui as nwg;
use native_windows_derive::NwgUi;
use nwg::NativeUi;
use reqwest::blocking::Client;
use serde_json::Value;
use std::{
    cell::RefCell,
    sync::{Arc, Mutex},
    thread,
    time::Duration,
};
use windows::{
    core::HSTRING,
    Foundation::Uri,
    Media::{Core::MediaSource, Playback::MediaPlayer},
};
mod update;

const API: &str = "https://primecloud.pigboss.xyz";
fn stream_player(url: &str) -> windows::core::Result<MediaPlayer> {
    let uri = Uri::CreateUri(&HSTRING::from(url))?;
    let source = MediaSource::CreateFromUri(&uri)?;
    let player = MediaPlayer::new()?;
    player.SetSource(&source)?;
    Ok(player)
}
type Failure = Box<dyn std::error::Error>;
enum PlayerEvent {
    SignedIn,
    Rows(Vec<Value>),
    Play(String, String),
    Message(String),
}
fn credential() -> Result<keyring::Entry, keyring::Error> {
    keyring::Entry::new("PrimeCloud", "session")
}
fn authenticated(client: &Client, path: &str, args: &[(&str, String)]) -> Result<Value, Failure> {
    let token = credential()?
        .get_password()
        .map_err(|_| "Сначала войдите через Telegram")?;
    let response = client
        .get(format!("{API}{path}"))
        .bearer_auth(token)
        .query(args)
        .send()?;
    let status = response.status();
    let data: Value = response.json()?;
    if !status.is_success() {
        return Err(data["error"]
            .as_str()
            .unwrap_or("Ошибка сервера")
            .to_owned()
            .into());
    }
    Ok(data)
}
fn login(client: &Client, method: &str) -> Result<PlayerEvent, Failure> {
    let info: Value = client
        .post(format!("{API}/auth/start"))
        .send()?
        .error_for_status()?
        .json()?;
    let url = info[method].as_str().ok_or("Не удалось создать запрос")?;
    let prefix = if method == "bot" {
        "https://t.me/PrimeCloud_robot?start="
    } else {
        "https://primecloud.pigboss.xyz/login/"
    };
    if !url.starts_with(prefix) {
        return Err("Неизвестный адрес входа".into());
    }
    open::that(url)?;
    for _ in 0..150 {
        thread::sleep(Duration::from_secs(2));
        let res = client
            .post(format!("{API}/auth/poll"))
            .bearer_auth(info["poll"].as_str().ok_or("Нет ключа входа")?)
            .send()?;
        if res.status().as_u16() == 202 {
            continue;
        }
        let data: Value = res.error_for_status()?.json()?;
        credential()?.set_password(data["token"].as_str().ok_or("Нет сессии")?)?;
        return Ok(PlayerEvent::SignedIn);
    }
    Err("Время входа истекло".into())
}

#[derive(Default, NwgUi)]
pub struct Player {
    #[nwg_control(size:(800,540), title:"PrimeCloud", flags:"WINDOW|VISIBLE")]
    #[nwg_events(OnWindowClose:[nwg::stop_thread_dispatch()])]
    window: nwg::Window,
    #[nwg_layout(parent:window, spacing:6)]
    grid: nwg::GridLayout,
    #[nwg_control(text:"Войти через бота")]
    #[nwg_layout_item(layout:grid,col:0,row:0,col_span:2)]
    #[nwg_events(OnButtonClick:[Player::bot])]
    bot_button: nwg::Button,
    #[nwg_control(text:"Войти через виджет")]
    #[nwg_layout_item(layout:grid,col:2,row:0,col_span:2)]
    #[nwg_events(OnButtonClick:[Player::widget])]
    widget_button: nwg::Button,
    #[nwg_control(focus:true)]
    #[nwg_layout_item(layout:grid,col:0,row:1,col_span:3)]
    query: nwg::TextInput,
    #[nwg_control(collection:vec!["Треки".to_string(),"Альбомы".to_string(),"Артисты".to_string()],selected_index:Some(0))]
    #[nwg_layout_item(layout:grid,col:3,row:1)]
    kind: nwg::ComboBox<String>,
    #[nwg_control(text:"Найти")]
    #[nwg_layout_item(layout:grid,col:4,row:1)]
    #[nwg_events(OnButtonClick:[Player::search])]
    search_button: nwg::Button,
    #[nwg_control]
    #[nwg_layout_item(layout:grid,col:0,row:2,col_span:5,row_span:8)]
    #[nwg_events(OnListBoxDoubleClick:[Player::select])]
    results: nwg::ListBox<String>,
    #[nwg_control(text:"Открыть / играть")]
    #[nwg_layout_item(layout:grid,col:0,row:10,col_span:2)]
    #[nwg_events(OnButtonClick:[Player::select])]
    play_button: nwg::Button,
    #[nwg_control(text:"Пауза")]
    #[nwg_layout_item(layout:grid,col:2,row:10)]
    #[nwg_events(OnButtonClick:[Player::pause])]
    pause_button: nwg::Button,
    #[nwg_control(text:"Продолжить")]
    #[nwg_layout_item(layout:grid,col:3,row:10)]
    #[nwg_events(OnButtonClick:[Player::resume])]
    resume_button: nwg::Button,
    #[nwg_control(text:"Фрагмент")]
    #[nwg_layout_item(layout:grid,col:4,row:10)]
    #[nwg_events(OnButtonClick:[Player::preview])]
    preview_button: nwg::Button,
    #[nwg_control(text:"Поиск по трекам, альбомам и исполнителям")]
    #[nwg_layout_item(layout:grid,col:0,row:11,col_span:5)]
    status: nwg::Label,
    #[nwg_control(parent:window)]
    #[nwg_events(OnNotice:[Player::receive])]
    wake: nwg::Notice,
    events: Arc<Mutex<Vec<PlayerEvent>>>,
    rows: RefCell<Vec<Value>>,
    media: RefCell<Option<MediaPlayer>>,
}
impl Player {
    fn run(&self, f: impl FnOnce(Client) -> Result<PlayerEvent, Failure> + Send + 'static) {
        self.search_button.set_enabled(false);
        self.bot_button.set_enabled(false);
        self.widget_button.set_enabled(false);
        self.play_button.set_enabled(false);
        self.results.set_enabled(false);
        self.status.set_text("Подождите…");
        let events = self.events.clone();
        let notice = self.wake.sender();
        thread::spawn(move || {
            let result = Client::builder()
                .user_agent("PrimeCloud/0.1")
                .timeout(Duration::from_secs(20))
                .build()
                .map_err(Failure::from)
                .and_then(f);
            events
                .lock()
                .unwrap()
                .push(result.unwrap_or_else(|e| PlayerEvent::Message(e.to_string())));
            notice.notice();
        });
    }
    fn receive(&self) {
        self.bot_button.set_enabled(true);
        self.widget_button.set_enabled(true);
        self.search_button.set_enabled(true);
        self.play_button.set_enabled(true);
        self.results.set_enabled(true);
        for event in self.events.lock().unwrap().drain(..) {
            match event {
                PlayerEvent::SignedIn => self
                    .status
                    .set_text("Вы вошли. Найдите трек, альбом или исполнителя."),
                PlayerEvent::Message(msg) => self.status.set_text(&msg),
                PlayerEvent::Rows(rows) => {
                    self.results.set_collection(
                        rows.iter()
                            .map(|r| {
                                format!(
                                    "{}  {}{}",
                                    r["artist"].as_str().unwrap_or(""),
                                    r["title"].as_str().unwrap_or(""),
                                    if r["explicit"] == true { "  [E]" } else { "" }
                                )
                            })
                            .collect(),
                    );
                    self.status.set_text(&format!("Найдено: {}", rows.len()));
                    *self.rows.borrow_mut() = rows;
                }
                PlayerEvent::Play(url, label) => self.listen(&url, &label),
            }
        }
    }
    fn bot(&self) {
        self.run(|c| login(&c, "bot"))
    }
    fn widget(&self) {
        self.run(|c| login(&c, "widget"))
    }
    fn search(&self) {
        let kind = ["track", "album", "artist"][self.kind.selection().unwrap_or(0)].to_string();
        let query = self.query.text();
        if query.trim().is_empty() {
            self.query.set_focus();
            return;
        }
        self.run(move |c| Self::listing(&c, "/api/search", &[("q", query), ("type", kind)]));
    }
    fn listing(c: &Client, path: &str, args: &[(&str, String)]) -> Result<PlayerEvent, Failure> {
        let mut data = authenticated(c, path, args)?;
        Ok(PlayerEvent::Rows(
            data["items"]
                .as_array_mut()
                .map(std::mem::take)
                .unwrap_or_default(),
        ))
    }
    fn selected(&self) -> Option<Value> {
        self.results
            .selection()
            .and_then(|i| self.rows.borrow().get(i).cloned())
    }
    fn select(&self) {
        let Some(row) = self.selected() else { return };
        self.run(move |c| {
            let args = [("id", row["id"].to_string())];
            match row["type"].as_str() {
                Some("artist") => Self::listing(&c, "/api/artist", &args),
                Some("album") => Self::listing(&c, "/api/album", &args),
                _ => {
                    let audio = authenticated(&c, "/api/listen", &args)?;
                    Ok(PlayerEvent::Play(
                        audio["url"]
                            .as_str()
                            .ok_or("Источник недоступен")?
                            .to_string(),
                        format!(
                            "{} · {}",
                            row["title"].as_str().unwrap_or(""),
                            audio["source"].as_str().unwrap_or("")
                        ),
                    ))
                }
            }
        });
    }
    fn preview(&self) {
        if let Some(r) = self.selected() {
            if let Some(u) = r["preview"].as_str().filter(|u| !u.is_empty()) {
                self.listen(u, "Фрагмент Deezer")
            } else {
                self.status.set_text("Фрагмент недоступен")
            }
        }
    }
    fn listen(&self, url: &str, label: &str) {
        let result = (|| -> windows::core::Result<()> {
            let player = stream_player(url)?;
            player.Play()?;
            if let Some(old) = self.media.replace(Some(player)) {
                let _ = old.Close();
            }
            Ok(())
        })();
        self.status.set_text(
            &result
                .map(|_| label.to_string())
                .unwrap_or_else(|e| e.to_string()),
        );
    }
    fn pause(&self) {
        if let Some(p) = self.media.borrow().as_ref() {
            let _ = p.Pause();
        }
    }
    fn resume(&self) {
        if let Some(p) = self.media.borrow().as_ref() {
            let _ = p.Play();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    #[ignore = "Requires a fresh full-track URL and a Windows audio device"]
    fn full_recording_plays_on_windows() {
        let player = stream_player(&std::env::var("PRIMECLOUD_TEST_AUDIO").unwrap()).unwrap();
        player.SetIsMuted(true).unwrap();
        player.Play().unwrap();
        let session = player.PlaybackSession().unwrap();
        let start = std::time::Instant::now();
        while start.elapsed() < Duration::from_secs(35) {
            let position = session.Position().unwrap().Duration;
            let duration = session.NaturalDuration().unwrap().Duration;
            if position > 12_000_000 && duration > 600_000_000 {
                println!(
                    "Windows playback {:.1} s / {:.1} s",
                    position as f64 / 1e7,
                    duration as f64 / 1e7
                );
                player.Close().unwrap();
                return;
            }
            thread::sleep(Duration::from_millis(200));
        }
        panic!("Playback did not advance through the full recording");
    }
}
fn main() {
    nwg::init().expect("Win32");
    let _ = nwg::Font::set_global_family("Segoe UI");
    let ui = Player::build_ui(Default::default()).expect("PrimeCloud UI");
    let notify = ui.wake.sender();
    let events = ui.events.clone();
    thread::spawn(move || {
        if let Ok(client) = Client::builder()
            .user_agent("PrimeCloud updater")
            .timeout(Duration::from_secs(60))
            .build()
        {
            if let Ok(true) = update::check(&client) {
                events.lock().unwrap().push(PlayerEvent::Message(
                    "Обновление установлено. Перезапустите PrimeCloud.".into(),
                ));
                notify.notice();
            }
        }
    });
    nwg::dispatch_thread_events()
}
