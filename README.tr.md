# Second Brain

Claude Code, Codex ve OpenCode için tüm projeler arasında ortak çalışan lokal AI hafıza katmanı.

Kurulumdan sonra agent'ları Second Brain klasöründe çalıştırmazsın; her projede eskisi gibi `claude`, `codex` veya `opencode` kullanmaya devam edersin.

## Kurulum

```bash
./install.sh \
  --name "Alex" \
  --path "$HOME/Documents/Second Brain" \
  --language tr \
  --checkpoint-minutes 10
```

Güncelleme:

```bash
./install.sh --path "$HOME/Documents/Second Brain" --language tr --upgrade
```

## Eski konuşmaları aktar

```bash
./import-history.sh "$HOME/Documents/Second Brain"
./compile-history.sh "$HOME/Documents/Second Brain" --limit 5
./compile-history.sh "$HOME/Documents/Second Brain"
```

Orijinal Claude/Codex JSONL transcript'leri `raw/history/` altında aynen korunur.

## Obsidian

`~/Documents/Second Brain` klasörünü vault olarak açman yeterli.

---

_Authored and maintained by [Doğan Koç](https://github.com/dogankoc)._
