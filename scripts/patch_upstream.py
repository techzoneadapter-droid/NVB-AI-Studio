"""Patch documented invalid duplicate TOML and bind upstream to loopback.

The version of sub2gen pinned by our installer contains duplicate
generation_routing.allowed_credential_kinds in setting_example.toml.
Use an exact-match patch rather than silently importing a modified fork.
"""
from pathlib import Path
import tomllib

path = Path("upstream-sub2gen/config/setting_example.toml")
raw = path.read_text(encoding="utf-8")
duplicate = 'allowed_credential_kinds = ["session_token", "browser_session", "oauth"]'
if raw.count("allowed_credential_kinds = ") != 2 or raw.count(duplicate) != 1:
    raise SystemExit("Unexpected upstream config; review before packaging.")
raw = raw.replace(duplicate + "\n", "")
if 'host = "0.0.0.0"' not in raw:
    raise SystemExit("Unexpected server host configuration.")
raw = raw.replace('host = "0.0.0.0"', 'host = "127.0.0.1"')
raw = raw.replace("log_requests = true", "log_requests = false")
raw = raw.replace("log_responses = true", "log_responses = false")
tomllib.loads(raw)
path.write_text(raw, encoding="utf-8")
print("Patched invalid upstream TOML and restricted engine to loopback.")

# Upstream imports these providers during startup but classifies them as dev-only.
# Promote them into production dependencies; CI re-locks the pinned workspace.
project = Path("upstream-sub2gen/pyproject.toml")
original = project.read_text(encoding="utf-8")
runtime, boundary, dev = original.partition("[dependency-groups]")
if not boundary:
    raise SystemExit("Upstream metadata changed; inspect manually.")
anchor = '  "sub2gen-worker-protocol",\n]'
if runtime.count(anchor) != 1:
    raise SystemExit("Unexpected runtime dependency marker.")
for name in ("sub2gen-provider-chatgpt", "sub2gen-image-worker"):
    line = '  "' + name + '",\n'
    if dev.count(line) != 1:
        raise SystemExit("Missing expected development dependency: " + name)
    dev = dev.replace(line, "", 1)
runtime = runtime.replace(anchor,
    '  "sub2gen-worker-protocol",\n  "sub2gen-provider-chatgpt",\n  "sub2gen-image-worker",\n]', 1)
updated = runtime + boundary + dev
metadata = tomllib.loads(updated)
for name in ("sub2gen-provider-chatgpt", "sub2gen-image-worker"):
    assert name in metadata["project"]["dependencies"]
    assert name not in metadata["dependency-groups"]["dev"]
project.write_text(updated, encoding="utf-8")
print("Bundled production dependencies now include eager-import providers.")


# Add a one-paste, explicitly user-approved NVB Quick Connect option to the
# extension. Keep the original generic sub2gen pairing settings fully intact.
# The bundle contains API + expiring pairing code; it is never logged or stored
# as a separate file, and the extension clears it from the input after use.
extension_html = Path("upstream-sub2gen/apps/captcha-extension/static/options.html")
html = extension_html.read_text(encoding="utf-8")
html_anchor = '        <form class="settings-form" id="settingsForm" novalidate>'
if html.count(html_anchor) != 1:
    raise SystemExit("sub2gen worker Options HTML changed; review before patch.")
card = '''        <section class="settings-card" aria-labelledby="nvbHeading">
          <div class="card-header">
            <h2 class="card-title" id="nvbHeading">NVB AI Studio · Kết nối nhanh</h2>
            <p class="card-description">Dán một mã từ nút KẾT NỐI GOOGLE FLOW trong ứng dụng Windows. Không nhập API key và Pairing code riêng.</p>
          </div>
          <div class="card-content">
            <label class="field">
              <span class="field-label">Mã kết nối NVB đã sao chép từ ứng dụng</span>
              <input class="input" id="nvbQuickPaste" type="password" autocomplete="off"
                     placeholder="NVB1...." spellcheck="false" />
            </label>
            <button class="button button-primary" id="nvbQuickConnect" type="button">Kết nối NVB AI Studio</button>
            <p class="inline-status" id="nvbQuickStatus" aria-live="polite">Chỉ dùng mã tạo trên máy của bạn, không chia sẻ mã này.</p>
          </div>
        </section>
'''
html = html.replace(html_anchor, html_anchor + "\n" + card, 1)
extension_html.write_text(html, encoding="utf-8")

extension_options = Path("upstream-sub2gen/apps/captcha-extension/src/options.ts")
option_source = extension_options.read_text(encoding="utf-8")
anchor = '  await updateConnectionStatus()\n}'
if option_source.count(anchor) != 1:
    raise SystemExit("sub2gen worker Options TypeScript changed; review before patch.")
option_source = option_source.replace(
    anchor,
    '''  element<HTMLButtonElement>("nvbQuickConnect").addEventListener("click", () => void nvbQuickConnect())
''' + anchor, 1,
)
quick_handler = r"""
async function nvbQuickConnect(): Promise<void> {
  const input = element<HTMLInputElement>("nvbQuickPaste")
  const status = element<HTMLParagraphElement>("nvbQuickStatus")
  const button = element<HTMLButtonElement>("nvbQuickConnect")
  button.disabled = true
  try {
    const raw = input.value.trim()
    if (!raw.startsWith("NVB1.")) throw new Error("Mã không hợp lệ. Hãy bấm KẾT NỐI GOOGLE FLOW trong app.")
    const token = raw.substring(5).replaceAll("-", "+").replaceAll("_", "/")
    const data = JSON.parse(atob(token))
    if (data.v !== 1 || data.server_url !== "ws://127.0.0.1:8000/worker_ws" ||
        typeof data.api_key !== "string" || !data.api_key.startsWith("s2g_") ||
        typeof data.pairing_code !== "string" || !data.pairing_code) {
      throw new Error("Mã NVB không đúng định dạng hoặc không dành cho local sub2gen.")
    }
    await saveStorage({
      serverUrl: data.server_url,
      pairingCode: data.pairing_code,
      apiKey: data.api_key,
      connectionMode: "endUser",
      clientLabel: "NVB Chrome",
      accountAutoImportEnabled: true,
      accountAutoImportIntervalMinutes: 30,
    })
    input.value = ""
    const connection = await runtimeMessage<RuntimeReply>({ type: "reconnect_now" })
    if (!connection.success) throw new Error(connection.error || "Không thể ghép Chrome với app.")
    const imported = await runtimeMessage<RuntimeReply>({ type: "import_current_account" })
    if (!imported.success) throw new Error(imported.error || "Chưa đồng bộ tài khoản Flow.")
    status.textContent = "Đã kết nối Chrome và đồng bộ tài khoản. Quay lại NVB AI Studio."
    status.dataset.tone = "positive"
    await updateConnectionStatus()
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "Không thể kết nối. Tạo mã mới trong app."
    status.dataset.tone = "negative"
  } finally {
    button.disabled = false
  }
}
"""
option_source=option_source.replace('document.addEventListener("DOMContentLoaded", () => void initialize())',quick_handler+'\ndocument.addEventListener("DOMContentLoaded", () => void initialize())')
extension_options.write_text(option_source, encoding="utf-8")
print("Patched sub2gen Chrome Options with one-paste NVB Quick Connect.")
