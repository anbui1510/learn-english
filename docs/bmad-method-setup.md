# BMAD-METHOD — LearnEnglish / Cursor

Hướng dẫn cài đặt BMad Method cho repo **learn-english** và dùng trong **Cursor**.

---

## Nguồn chính thức | Official source

| | |
|---|---|
| **Repo** | https://github.com/bmad-code-org/BMAD-METHOD |
| **Phiên bản đã cài** | V7 preview (skills CLI), modules **core-tools** + **method** @ `6.13.0-next` |
| **Lựa chọn ổn định (khác)** | `npx bmad-method install` — xem nhánh [V6.12](https://github.com/bmad-code-org/BMAD-METHOD/tree/V6.12) |

Chúng ta dùng **đường cài V7** vì Cursor hỗ trợ **skills** (khuyến nghị trên README `main`).

---

## Yêu cầu | Prerequisites

- **Node.js** ≥ 20.12 (máy đã có v22)
- **npm** (cho `npx skills`)
- **Git**
- **[uv](https://docs.astral.sh/uv/)** — bắt buộc cho `bmad setup` và script Python của BMad

Cài uv (một lần):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# Thêm PATH (hoặc mở terminal mới):
export PATH="$HOME/.local/bin:$PATH"
```

---

## Lệnh đã chạy | Commands run

Trong thư mục gốc repo `learn-english`:

```bash
# 1) Skills: core + method (Cursor, không tương tác)
npx skills add bmad-code-org/BMAD-METHOD/skills/core-tools --skill '*' --agent cursor -y
npx skills add bmad-code-org/BMAD-METHOD/skills/method --skill '*' --agent cursor -y

# 2) Bootstrap runtime + _bmad/ (thay cho "bmad setup" trong chat)
export PATH="$HOME/.local/bin:$PATH"
SKILL_ROOT=".agents/skills/bmad"
uv run --no-cache "$SKILL_ROOT/scripts/setup.py" \
  --project-root "$(pwd)" \
  --skill "$SKILL_ROOT" \
  --root ".agents/skills"

# 3) Kiểm tra (current: true)
uv run --no-cache "$SKILL_ROOT/scripts/setup.py" \
  --project-root "$(pwd)" \
  --skill "$SKILL_ROOT" \
  --root ".agents/skills" \
  --status
```

Kết quả kiểm tra: `bmad_exists: true`, `current: true`, không có `pending_questions`.

---

## File nằm ở đâu | Where files live

| Đường dẫn | Mục đích |
|-----------|----------|
| `.agents/skills/` | Bản sao skills BMad cho Cursor (28 skills: `bmad`, `bmad-build`, agents, …) |
| `skills-lock.json` | Khóa phiên bản / nguồn skills (để `npx skills update` đồng bộ) |
| `_bmad/config.toml` | Cấu hình dự án (`project_name = "learn-english"`, `output_folder`) |
| `_bmad/scripts/` | Script dùng chung (setup, config, …) |
| `_bmad/core-tools/`, `_bmad/method/` | Script theo module |
| `_bmad/custom/` | Tùy biến team/user (`*.user.toml` không commit) |
| `_bmad-output/` | Artefact kế hoạch / build (đã `.gitignore`) |

Tài liệu tham khảo upstream: [Install BMad](https://docs.bmad-method.org/) (trang tương đương `docs/start/install-bmad.md` trên GitHub).

---

## Bước tiếp theo trong Cursor | Next steps in Cursor

1. **Mở** thư mục `learn-english` trong Cursor (Agent mode).

2. **Cập nhật / sửa cài đặt:** trong chat, nhắn skill **`bmad`**:
   - `bmad setup` — cập nhật module, câu hỏi cấu hình mới
   - `bmad status` — kiểm tra phiên bản

3. **Bắt đầu làm việc:**
   - Gọi **`bmad-build`** (hoặc nhờ agent đọc skill `bmad-build`) với mô tả thay đổi bạn muốn.
   - Hỏi **`bmad`** khi không chắc bước tiếp theo (planning vs build trực tiếp).

4. **Dự án có sẵn mã:** xem [Start in an Existing Codebase](https://docs.bmad-method.org/existing-codebases/start-in-an-existing-codebase/) và skill `bmad-project-context` khi cần `AGENTS.md`.

5. **Cập nhật skills sau này:**

   ```bash
   npx skills update -p -y
   # Rồi trong Cursor: bmad setup
   ```

---

## Ghi chú bảo mật | Security note

Khi `npx skills add`, bảng **Security Risk Assessments** là bình thường — một số skill chạy script Python từ `_bmad/`. Chi tiết: https://skills.sh/bmad-code-org/BMAD-METHOD

---

## Cài lại trên máy khác | Reinstall on another machine

```bash
git clone https://github.com/anbui1510/learn-english.git
cd learn-english
# Nếu repo đã có .agents/ + _bmad/ + skills-lock.json từ PR:
# — Mở Cursor là dùng được.
# Hoặc chỉ cần lock file:
npx skills experimental_install   # nếu CLI hỗ trợ restore từ lock
export PATH="$HOME/.local/bin:$PATH"
# Sau đó: bmad setup trong Cursor
```

---

*Cập nhật: 2026-11-14 — Cloud agent cài BMAD cho LearnEnglish.*