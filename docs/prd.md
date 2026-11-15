# PRD: Nền tảng học tiếng Anh giao tiếp y khoa (LearnEnglish)

| | |
|---|---|
| **Phiên bản** | 1.0 |
| **Ngày** | 2026-11-15 |
| **Nguồn** | [brief.md](/cursor/stores/self/docs/brief.md) v1.2 |
| **Repo** | `anbui1510/learn-english` |
| **Horizon MVP** | ~90 ngày (MVP B) |

---

## 1. Tổng quan sản phẩm

### 1.1 Vision

Web app giúp **bác sĩ nội trú** luyện tiếng Anh giao tiếp y khoa từ tài liệu chính thống (bắt đầu *Nelson Textbook of Pediatrics*): upload PDF → fact có truy vết → hội thoại 1–3 bối cảnh → karaoke + shadowing; sau đó chấm phát âm, role-play, và gamification học sâu.

### 1.2 Nguyên tắc sản phẩm (non-negotiable)

1. **Không suy diễn** ngoài nguồn PDF đã duyệt.
2. Mọi nội dung publish có **metadata ISBN, edition, trang** (và chương/mục khi có).
3. **Editor duyệt** fact (và preview dialogue khi cần) **trước publish**.
4. Mọi câu dialogue publish **liên kết ≥ 1 fact card** đã `verified`.
5. Phần thưởng gamification = **mở khóa nội dung**, không cosmetic.

### 1.3 Personas

| Persona | Mô tả | Vai trò hệ thống |
|---------|--------|-------------------|
| **Resident Learner** | Bác sĩ nội trú, chọn CEFR, lộ trình 6 tháng | `learner` |
| **Clinical Editor** | Bác sĩ/người dùng được gán quyền duyệt nội dung | `editor` |
| **Platform Admin** | Quản trị user, sách, cấu hình | `admin` |

### 1.4 Giai đoạn phát hành

| Giai đoạn | Tên | Mục tiêu |
|-----------|-----|----------|
| **G1** | **MVP B** (~90 ngày) | Pipeline nội dung + karaoke + shadowing + nền ghi âm/role-play |
| **G2** | **Pha 2** | Azure PA, scoring đa chiều, SRS, gamification |
| **G3** | **Roadmap** | 10 phút, Remotion, đa sách, mobile, TTS premium |

**Quy ước ID story:** `US-G1-###` (MVP), `US-G2-###` (Pha 2), `US-G3-###` (Roadmap).

---

## 2. Epic map theo giai đoạn

### Giai đoạn 1 — MVP B

| Epic ID | Epic | Mô tả ngắn |
|---------|------|------------|
| **E-G1-01** | Identity & access | Google OAuth, RBAC |
| **E-G1-02** | PDF ingest & storage | Upload Nelson, GCS |
| **E-G1-03** | Clinical fact extraction | Docling + fact cards |
| **E-G1-04** | Editorial workflow | Review, publish gate |
| **E-G1-05** | Case & dialogue generation | 3 bối cảnh, CEFR, Gemini |
| **E-G1-06** | Speech synthesis | edge-tts, timestamps |
| **E-G1-07** | Karaoke learning experience | Player, song ngữ, tốc độ |
| **E-G1-08** | Shadowing practice | 10 thẻ / bài |
| **E-G1-09** | Learner journey config | 6 tháng, bài/tuần |
| **E-G1-10** | Learning foundation | Attempt, ghi âm, role-play placeholder |

### Giai đoạn 2 — Pha 2

| Epic ID | Epic | Mô tả ngắn |
|---------|------|------------|
| **E-G2-01** | Pronunciation assessment | Azure Speech PA |
| **E-G2-02** | Role-play & multi-score | Read-along + free + empathy |
| **E-G2-03** | Visual feedback & replay | Đỏ/xanh/vàng, tap-to-replay |
| **E-G2-04** | Spaced repetition | Ôn lại T+1 |
| **E-G2-05** | Progression & unlocks | Case hiếm, điều kiện module |
| **E-G2-06** | Ranks & CME ảo | Danh hiệu, chứng nhận số |
| **E-G2-07** | Specialty skill trees | Module đại cương → chuyên sâu |

### Giai đoạn 3 — Roadmap

| Epic ID | Epic | Mô tả ngắn |
|---------|------|------------|
| **E-G3-01** | Extended session length | ~10 phút / bài |
| **E-G3-02** | Video export | Remotion MP4 1080p |
| **E-G3-03** | Multi-source library | Harriet Lane, WHO, guideline |
| **E-G3-04** | Mobile apps | iOS/Android |
| **E-G3-05** | Premium voice & studio | ElevenLabs, giọng thật |

---

## 3. Giai đoạn 1 (MVP B) — Epics & User Stories

### Epic E-G1-01: Identity & access

**Mục tiêu:** Người dùng đăng nhập an toàn; phân quyền rõ cho learner / editor / admin.

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G1-001 | Là **resident**, tôi đăng nhập bằng **Google account**, để không tạo mật khẩu riêng. | OAuth hoàn tất; session JWT/httpOnly; logout hoạt động. |
| US-G1-002 | Là **admin**, tôi gán role **editor** hoặc **learner** cho user, để editor có thể là user bình thường. | CRUD role; editor ≠ chỉ admin; audit log tối thiểu (who/when). |
| US-G1-003 | Là **hệ thống**, tôi chặn API theo role, để learner không upload/duyệt nếu chưa được cấp quyền. | 403 trên endpoint editor-only; integration test role matrix. |

---

### Epic E-G1-02: PDF ingest & storage

**Mục tiêu:** Upload PDF hợp pháp, lưu GCS, gắn metadata sách.

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G1-010 | Là **editor**, tôi upload **PDF chương/mục** Nelson, để tạo ca lâm sàng mới. | Giới hạn MIME `application/pdf`; max size cấu hình; lưu GCS; bản ghi `Case` draft. |
| US-G1-011 | Là **editor**, tôi nhập **ISBN, edition**, để mọi fact sau này kế thừa metadata. | Bắt buộc trước extract; hiển thị trên UI learner. |
| US-G1-012 | Là **admin**, tôi cấu hình bucket/region GCP, để PDF không lưu trên máy client. | Chỉ signed URL/time-limited cho download nội bộ editor. |

---

### Epic E-G1-03: Clinical fact extraction

**Mục tiêu:** Trích fact cards bám sách, không suy diễn.

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G1-020 | Là **editor**, tôi bấm **Trích xuất** sau upload, để hệ thống tạo fact cards từ PDF. | Docling (hoặc tương đương) phân đoạn theo heading lâm sàng; job async + trạng thái. |
| US-G1-021 | Là **hệ thống**, mỗi fact có `source_quote`, `atomic_fact`, `category`, **trang**, `status`, để đáp schema brief. | JSON schema validate; `needs_review` mặc định; mơ hồ → bỏ qua hoặc `needs_review`. |
| US-G1-022 | Là **editor**, tôi xem danh sách fact kèm **trích dẫn + số trang**, để đối chiếu sách. | UI sort/filter theo category/status; link “mở đoạn PDF” (nếu có viewer). |

---

### Epic E-G1-04: Editorial workflow

**Mục tiêu:** Human-in-the-loop trước khi sinh dialogue cho learner.

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G1-030 | Là **editor**, tôi **duyệt / từ chối / sửa** từng fact, để chỉ `verified` được dùng. | PATCH fact; lịch sử trạng thái; không publish case nếu còn fact bắt buộc chưa verified. |
| US-G1-031 | Là **hệ thống**, tôi **chặn** `generate-dialogues` khi case chưa **published**, để không lộ nội dung thô. | API trả 409 + message; test e2e gate. |
| US-G1-032 | Là **editor**, tôi **publish** case, để learner thấy bài. | Trạng thái `published`; timestamp + editor_id. |

---

### Epic E-G1-05: Case & dialogue generation

**Mục tiêu:** Một ca lâm sàng; 1–3 bối cảnh; ~2 phút; CEFR; song ngữ tùy chọn.

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G1-040 | Là **editor/learner** (theo policy), tôi chọn **1–3 bối cảnh**: bệnh nhân/thân nhân, đồng nghiệp (+SBAR), chuyên gia/CME, để sinh đúng clip cần học. | Checkbox 3 loại; sinh 1–3 dialogue artifacts. |
| US-G1-041 | Là **hệ thống**, tôi sinh dialogue bằng **Gemini structured output** chỉ từ fact `verified`, để không hallucinate. | Mỗi line có `fact_ids[]`; validate không rỗng; 3 system prompt riêng bối cảnh. |
| US-G1-042 | Là **learner**, tôi chọn **CEFR level** (3 gói), để từ vựng, độ dài, formal khớp level. | Tag `cefr_level` trên output; A2 đơn giản hơn C1; preview khác nhau. |
| US-G1-043 | Là **learner**, tôi **bật/tắt** phụ đề tiếng Việt, để đối chiếu nhưng vẫn ưu tiên tiếng Anh. | Toggle per session; VI không thay EN audio. |
| US-G1-044 | Là **hệ thống**, dialogue **~2 phút** đọc ở tốc độ 1x, để trong scope MVP. | Ước lượng duration; cảnh báo editor nếu vượt ngưỡng. |

---

### Epic E-G1-06: Speech synthesis

**Mục tiêu:** Audio per line; karaoke timestamps; giọng demo.

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G1-050 | Là **hệ thống**, tôi tổng hợp giọng **edge-tts**: Guy (bác sĩ/đồng nghiệp nam), Jenny (thân nhân nữ), để đủ vai demo. | MP3 per utterance; cache GCS; idempotent re-synth. |
| US-G1-051 | Là **hệ thống**, tôi xuất `timestamps.json` (WordBoundary, ms), để karaoke highlight từng từ. | Đồng bộ player; drift &lt; 150ms trên mẫu QA. |
| US-G1-052 | Là **learner**, tôi nghe **concatenated** dialogue theo thứ tự vai, để luyện nghe liên tục. | Playlist API; speaker role metadata. |

---

### Epic E-G1-07: Karaoke learning experience

**Mục tiêu:** Player tương tác, highlight, tốc độ.

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G1-060 | Là **learner**, tôi xem **karaoke player** với scene phòng khám và vai đang nói được highlight, để dễ theo dõi. | UI 2 vai; màu khác (teal/cam hoặc tương đương). |
| US-G1-061 | Là **learner**, tôi thấy **từ đang phát** đổi màu theo audio, để luyện đọc theo nhịp. | Word-level sync từ timestamps. |
| US-G1-062 | Là **learner**, tôi chỉnh tốc độ **0.5×–1.25×**, để phù hợp trình độ. | Pitch/time stretch; timestamps scale. |
| US-G1-063 | Là **learner**, tôi thấy **ISBN, trang, edition** trên bài, để biết nguồn. | Watermark/metadata hiển thị cố định. |

---

### Epic E-G1-08: Shadowing practice

**Mục tiêu:** 10 thẻ cuối bài; collocation; SBAR mẫu.

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G1-070 | Là **hệ thống**, tôi chọn **10 cụm** `is_key_phrase: true` từ dialogue, để shadowing có nội dung. | Tối thiểu 1 SBAR line nếu bối cảnh 2; mix collocation. |
| US-G1-071 | Là **learner**, tôi luyện trên **lưới 2 cột** với chế độ **đuổi tự động** hoặc bấm từng thẻ, để lặp nhanh. | Autoplay queue; pause/skip. |
| US-G1-072 | Là **learner**, tôi nghe mẫu AI cho từng thẻ trước khi nói theo, để shadowing đúng chuẩn. | Play per card; same TTS cache. |

---

### Epic E-G1-09: Learner journey config

**Mục tiêu:** Lộ trình 6 tháng; tự chọn nhịp học.

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G1-080 | Là **learner**, tôi đặt **số bài/tuần** và xem lộ trình **6 tháng**, để tự quản lý tiến độ. | Profile settings; dashboard “tuần này”. |
| US-G1-081 | Là **learner**, tôi đánh dấu bài **hoàn thành** sau karaoke + shadowing, để theo dõi tiến độ. | Completion event; không yêu cầu chấm điểm G2. |
| US-G1-082 | Là **learner**, tôi duyệt **thư viện case đã publish**, để chọn bài mới. | List/filter; chỉ `published`. |

---

### Epic E-G1-10: Learning foundation (chuẩn bị Pha 2)

**Mục tiêu:** Ghi âm + Attempt + UI role-play placeholder; không Azure PA đầy đủ.

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G1-090 | Là **learner**, tôi **ghi âm** trên shadowing/role-play bằng RecordRTC/Web Speech, để luyện nói ngay từ MVP. | Upload `POST /attempts/audio`; lưu GCS + DB `LearningAttempt`. |
| US-G1-091 | Là **learner**, tôi mở màn **role-play split** (AI script một bên, micro một bên), để làm quen UX. | Placeholder: không chấm điểm; hiển thị “Pha 2 sắp có”. |
| US-G1-092 | Là **hệ thống**, schema **LearningAttempt** lưu `case_id`, `dialogue_id`, `mode`, `audio_uri`, để Pha 2 gắn Azure. | Migration SQL; API documented. |

---

### MVP B — Tiêu chí hoàn thành giai đoạn (Definition of Done)

- [ ] Một ca Nelson đi full flow: upload → extract → edit verify → publish → generate 3 bối cảnh (tùy chọn) → TTS → learner karaoke + 10 shadowing.
- [ ] Không có dialogue publish thiếu `fact_ids` hoặc thiếu metadata ISBN/trang.
- [ ] Learner hoàn thành ≥1 bài/tuần (cấu hình) trên môi trường staging.
- [ ] Ghi âm lưu được Attempt; role-play UI hiển thị (placeholder).

---

## 4. Giai đoạn 2 (Pha 2) — Epics & User Stories

### Epic E-G2-01: Pronunciation assessment

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G2-001 | Là **learner**, sau khi ghi âm, tôi nhận **điểm Azure PA** (pronunciation, completeness, prosody), để biết mức chính xác. | Gọi Azure SDK server-side; không lộ key client. |
| US-G2-002 | Là **hệ thống**, với **CEFR cao**, tôi đánh giá **stress_pattern** trên thuật ngữ dài, để ví dụ *electro**car**diogram* đúng trọng âm. | C1 lines store `stress_pattern` (lesson playlist + karaoke underline); PA `stress_hint` only when prosody &lt;75 or stressed word not green. |
| US-G2-003 | Là **admin**, tôi giới hạn **số lần chấm/phút** mỗi user/ngày, để kiểm soát chi phí Azure. | Rate limit + metric dashboard. |

---

### Epic E-G2-02: Role-play & multi-score

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G2-010 | Là **learner**, tôi role-play **read-along** (đọc script), để luyện accuracy. | So khớp reference text; PA word-level. |
| US-G2-011 | Là **learner**, tôi role-play **free response**, để luyện giao tiếp tự do. | Transcript STT; không bắt buộc khớp 100% script. |
| US-G2-012 | Là **hệ thống**, với free response, tôi chấm **Empathy** bằng LLM rubric, để đánh giá trấn an/lịch sự (đặc biệt báo tin xấu). | `USE_GEMINI_EMPATHY` + `GEMINI_API_KEY` → Gemini structured rubric; synthetic fallback on failure; coaching tip when &lt;75; disclaimer. |

---

### Epic E-G2-03: Visual feedback & replay

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G2-020 | Là **learner**, tôi thấy từ **xanh** (đúng), **đỏ** (sai), **vàng** (ngập), để sửa nhanh. | Map từ PA scores. |
| US-G2-021 | Là **learner**, tôi **chạm từ đỏ** để nghe lại mẫu AI, để sửa phát âm. | Snippet TTS cached per word/phrase. |
| US-G2-022 | Là **learner** level cao, tôi nhận gợi ý **ngữ điệu đồng cảm** khi empathy thấp, để cải thiện giao tiếp lâm sàng. | Gợi ý text + optional audio mẫu. |

---

### Epic E-G2-04: Spaced repetition (SRS)

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G2-030 | Là **hệ thống**, cụm **sai/ấp úng** tự vào **「Thẻ cần ôn lại」** ngày **T+1**, để lặp có khoảng cách. | Cron/scheduler; dedupe phrase. |
| US-G2-031 | Là **learner**, tôi thấy hàng đợi ôn trên dashboard, để ưu tiên yếu điểm. | Mark done advances SM-2 lite intervals (1→3→7→14); `repetition` on card; PA miss resets. |

---

### Epic E-G2-05: Progression & content unlocks

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G2-040 | Là **learner**, khi hoàn thành **chuỗi 7 ngày** module (vd. tim bẩm sinh cơ bản), tôi **mở khóa case** chuyên sâu (vd. VSD phức tạp), để động lực học sâu hơn. | Rule engine prerequisites; không cosmetic reward. |
| US-G2-041 | Là **admin/editor**, tôi gán **điều kiện mở khóa** cho case (module, CME, rank), để cấu hình lộ trình. | Admin UI; validation không cycle. |

---

### Epic E-G2-06: Ranks & CME ảo

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G2-050 | Là **learner**, tôi thăng **danh hiệu** Medical Student → … → Chief of Staff, để thấy tiến bộ. | Rule: cases completed + PA avg + required modules. |
| US-G2-051 | Là **learner**, tôi tích **CME points ảo** khi hoàn thành case (karaoke + shadowing + role-play đạt ngưỡng), để gamify đúng nghĩa học thuật. | Points ledger; configurable thresholds. |
| US-G2-052 | Là **learner**, khi đủ điểm module, tôi nhận **Digital Certificate** chia sẻ LinkedIn/FB, với disclaimer **không thay CME chính thức**. | PDF/OG render; public share link optional. |

---

### Epic E-G2-07: Specialty skill trees

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G2-060 | Là **learner**, tôi hoàn thành **Nhi đại cương** (Sốt, Tiêu chảy, Hô hấp) trước khi vào **Tim mạch nhi**, để học có trật tự. | Tree UI; locked nodes; map chapter Nelson. |
| US-G2-061 | Là **editor**, tôi gán case vào **module/nhánh** cây kỹ năng, để nội dung có cấu trúc. | Module–Case many-to-one; prerequisites. |

---

### Pha 2 — Definition of Done

- [x] Role-play có chấm Accuracy + (free) Empathy; feedback đỏ/xanh/vàng.
- [x] SRS T+1 hoạt động từ dữ liệu PA (synthetic mặc định; Azure khi `USE_AZURE_PA`).
- [x] Ít nhất **một** luồng unlock case + rank + CME cert end-to-end (API + UI).
- [x] Chi phí PA được log theo user/ngày (`GET /admin/pa-usage`).

---

## 5. Giai đoạn 3 (Roadmap) — Epics & User Stories

### Epic E-G3-01: Extended session length

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G3-001 | Là **learner**, tôi chọn phiên **~10 phút** kiểu thuyết trình/CME, để luyện presentation. | Generate prompt + TTS chunking; UI progress cho session dài. |

### Epic E-G3-02: Video export (Remotion)

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G3-010 | Là **learner/editor**, tôi xuất **MP4 1080p** từ karaoke + shadowing, để chia sẻ đồng nghiệp. | Remotion composition (`video/remotion`) + ffmpeg fallback; `POST /learner/dialogues/{id}/export-video`; job status. |

### Epic E-G3-03: Multi-source library

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G3-020 | Là **admin**, tôi thêm **nguồn sách** (Harriet Lane, WHO, guideline), để mở rộng thư viện. | `BookSource` entity; metadata ISBN per source; cùng pipeline fact. |

### Epic E-G3-04: Mobile apps

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G3-030 | Là **learner**, tôi học trên **app mobile** với karaoke + shadowing, để học khi di chuyển. | Capacitor Android+iOS shells; mic permissions; CORS; OAuth deep-link + `/auth/exchange`; offline karaoke cache (last 3 dialogues + audio blobs); API parity. |

### Epic E-G3-05: Premium voice

| ID | User Story | Acceptance Criteria |
|----|------------|---------------------|
| US-G3-040 | Là **learner**, tôi chọn **ElevenLabs/Azure** thay edge-tts, để chất lượng giọng cao hơn. | Provider abstraction; cost flag per org. |

---

## 6. Yêu cầu phi chức năng (NFR)

| ID | Hạng mục | MVP | Pha 2 |
|----|---------|-----|-------|
| NFR-01 | Bảo mật | OAuth, RBAC, signed URL GCS | Mã hóa audio at rest; PII tối thiểu |
| NFR-02 | Hiệu năng | Generate dialogue &lt; 2 phút SLA nội bộ (TBD) | Azure async scoring &lt; 10s/30s audio |
| NFR-03 | Chi phí | edge-tts + Gemini free tier ưu tiên | Azure metering, retry cap |
| NFR-04 | Khả dụng | Web desktop-first responsive | Mobile roadmap |
| NFR-05 | Tuân thủ nội dung | 100% fact traceability trên publish | Audit sample không mismatch |
| NFR-06 | Khả dụng truy cập | Karaoke region: keyboard ←/→/Home/End, focus ring, live line announce, ≥4.5:1 active word; see `docs/a11y-karaoke.md` | Cải thiện liên tục |

---

## 7. Phụ thuộc & stack (tham chiếu brief)

- **Backend:** FastAPI, Docling, google-genai, edge-tts (G1); Azure Speech PA, SRS cron (G2).
- **Frontend:** Vite, React, TypeScript, Tailwind, RecordRTC (G1–G2).
- **Data:** GCS + Cloud SQL; Google OAuth.
- **Dev process:** Cursor + BMAD trong `learn-english`.

---

## 8. Out of scope (tất cả giai đoạn hiện tại)

- Thay thế đào tạo lâm sàng / CME được cấp phép chính thức.
- Phân phối PDF Nelson cho learner nếu license không cho phép.
- Gamification cosmetic (avatar shop, kim cương).
- Chẩn đoán / điều trị thật cho bệnh nhân thật qua app.

---

## 9. Lịch epic đề xuất (MVP 90 ngày — gợi ý PM)

| Tuần | Epics ưu tiên |
|------|----------------|
| 1–2 | E-G1-01, E-G1-02, schemas |
| 3–5 | E-G1-03, E-G1-04 |
| 6–8 | E-G1-05, E-G1-06 |
| 9–11 | E-G1-07, E-G1-08 |
| 12 | E-G1-09, E-G1-10, hardening, DoD MVP |

**Pha 2:** Bắt đầu sau DoD MVP; thứ tự khuyến nghị E-G2-01 → E-G2-03 → E-G2-04 → E-G2-02 → E-G2-05…07 (theo brief §13).

---

## 10. Traceability

| Brief section | PRD coverage |
|---------------|--------------|
| §4 Pipeline | E-G1-02 … E-G1-08 |
| §5 MVP / Pha 2 / Roadmap | §2, §3, §4, §5 |
| §10 Stack | §7 |
| §11 Learning loop | E-G1-10, E-G2-01 … E-G2-04 |
| §12 Gamification | E-G2-05 … E-G2-07 |

---

*Tài liệu này là nguồn truth cho backlog. User Story có thể đưa vào Jira/Linear với prefix Epic ID.*