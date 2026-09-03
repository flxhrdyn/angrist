# Angrist Demo Scenario & VHS Recording

Petunjuk menjalankan demo skenario dan merekam terminal animation (GIF) menggunakan **VHS**.

---

## 🎯 Skenario Demo

File target: [`demo/calculator.py`](calculator.py)
Terdapat fungsi dengan bug:
1. `calculate_discount(price, discount_rate)`: Menggunakan `+` (pertambahan) bukan `-` (pengurangan).
2. Kelas `BankAccount`:
   - Atribut `BANK_CODE` dan method `deposit` yang valid.
   - Method `withdraw` dengan kondisi terbalik (`if amount < self.balance`).

Saat `angrist` dijalankan:
- AST Guard mengisolasi hanya node fungsi/method target.
- Worktree Sandbox menguji perubahan di direktori temp tanpa mengotori repo utama.
- Sibling method (`deposit`), class attribute (`BANK_CODE`), dan kode lain di luar target tetap terkunci secara deterministik (byte-identical).

---

## 🚀 Cara 1: Rekam Otomatis Menggunakan VHS

Jika Anda memiliki `vhs` terpasang di sistem, cukup jalankan perintah berikut di root repository:

```bash
vhs demo.tape
```

VHS akan otomatis:
1. Menjalankan mock OpenAI server lokal di background (`http://127.0.0.1:8089`).
2. Menampilkan kegagalan unit test sebelum perbaikan (`pytest demo/test_calculator.py -k test_calculate_discount`).
3. Menjalankan `angrist` untuk melakukan micro-fix secara otomatis ke fungsi `calculate_discount`.
4. Menjalankan kembali unit test untuk membuktikan test sekarang lulus (**PASSED**).
5. Menampilkan `git diff` yang membuktikan **hanya** node target yang disentuh.
6. Menyimpan hasil rekaman ke file [`demo.gif`](../demo.gif).

---

## 🛠 Cara 2: Menjalankan Demo Secara Manual

### Menggunakan Mock Server Lokal (Tanpa Butuh API Key)

1. Jalankan mock server di terminal terpisah:
   ```bash
   python demo/mock_server.py 8089
   ```

2. Cek kegagalan test:
   ```bash
   pytest demo/test_calculator.py -k test_calculate_discount
   ```

3. Jalankan `angrist` micro-fix:
   - PowerShell:
     ```powershell
     $env:ANGRIST_LLM_BASE_URL="http://127.0.0.1:8089"
     angrist --file demo/calculator.py --target calculate_discount --instruction "fix discount subtraction" --test-cmd "pytest demo/test_calculator.py -k test_calculate_discount" --lint-cmd "python -c pass" --auto-merge
     ```
   - Bash/Linux/macOS:
     ```bash
     export ANGRIST_LLM_BASE_URL="http://127.0.0.1:8089"
     angrist --file demo/calculator.py --target calculate_discount --instruction "fix discount subtraction" --test-cmd "pytest demo/test_calculator.py -k test_calculate_discount" --lint-cmd "python -c pass" --auto-merge
     ```

4. Verifikasi test telah berhasil:
   ```bash
   pytest demo/test_calculator.py -k test_calculate_discount
   ```

---

### Menggunakan Model Riil (Groq API)

Jika ingin mendemokan dengan model LLM sungguhan (Groq free tier):

1. Set environment variable:
   ```bash
   export ANGRIST_LLM_API_KEY="gsk_your_api_key_here"
   export ANGRIST_LLM_MODEL="llama-3.3-70b-versatile" # atau model OpenAI-compatible lainnya
   ```

2. Jalankan `angrist`:
   ```bash
   angrist --file demo/calculator.py \
           --target calculate_discount \
           --instruction "fix discount calculation: subtract discount amount from price" \
           --test-cmd "pytest demo/test_calculator.py -k test_calculate_discount" \
           --auto-merge
   ```

---

## 🔄 Mereset Demo ke Keadaan Semula

Untuk mengembalikan file `demo/calculator.py` kembali ke kondisi bug semula:

```bash
git checkout demo/calculator.py
```
atau
```bash
git restore demo/calculator.py
```
