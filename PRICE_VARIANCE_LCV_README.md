# Price Variance LCV - Avtomatik Yaratish

## 📋 Umumiy Ma'lumot

Bu modul Purchase Invoice va Purchase Receipt o'rtasidagi narx farqini avtomatik aniqlaydi va Landed Cost Voucher (LCV) yaratadi. Bu inventory valuation ni to'g'ri saqlash va moliyaviy hisobotlarni aniq yuritish uchun zarur.

## 🎯 Qanday Ishlaydi?

### Real Hayot Misoli:
1. **Purchase Receipt**: Maxsulot omborda qabul qilindi - 50 USD/dona
2. **Purchase Invoice**: Vaqt o'tgandan keyin invoice keladi - 60 USD/dona
3. **Natija**: 10 USD/dona narx farqi aniqlandi
4. **Avtomatik Harakat**: LCV yaratiladi va item tannarxi yangilanadi

## ✨ Asosiy Xususiyatlar

### 1. **Aniq Item Matching**
- `purchase_receipt_item` field orqali to'g'ri item-line matching
- Bir xil item bir PR da bir necha bor bo'lsa ham to'g'ri ishlaydi

### 2. **Multi-PR Support**
- Har bir Purchase Receipt uchun alohida LCV yaratiladi
- Bir PI da bir necha PR bo'lsa ham to'g'ri ishlaydi

### 3. **Currency Conversion**
- PI dagi `conversion_rate` avtomatik ishlatiladi
- UZS → USD va boshqa valyuta konversiyalari qo'llab-quvvatlanadi
- LCV company currency da (masalan, USD) yaratiladi

### 4. **Item-Specific Distribution (Yo'l A)**
- Faqat narx o'zgargan itemlarga variance distribute qilinadi
- Narx o'zgarmagan itemlar 0 variance oladi
- Eng aniq va professional usul

### 5. **Duplicate Prevention**
- Bir PI uchun bir marta LCV yaratiladi
- Qayta submit qilishda duplicate LCV yaratilmaydi

### 6. **Cancel Handling**
- PI cancel qilinganda linked LCV lar avtomatik cancel bo'ladi
- Xatolik bo'lsa log va notification beradi

## 🚀 O'rnatish (Setup)

### 1. Custom Field Yaratish

```bash
# Frappe bench directory da
cd /home/user/frappe-bench

# Bench console ochish
bench --site [your-site-name] console

# Console da:
from premierprint.setup.custom_fields import setup_all
setup_all()
exit()
```

**Yoki manual:**

**Purchase Invoice** DocType ga quyidagi Custom Field qo'shing:
- **Fieldname**: `custom_price_variance_lcvs`
- **Label**: Price Variance LCVs
- **Fieldtype**: Long Text
- **Read Only**: ✓
- **Hidden**: ✓
- **No Copy**: ✓
- **Print Hide**: ✓

### 2. App Restart

```bash
bench restart
```

## 📊 Foydalanish

### Oddiy Scenario:

1. **Purchase Receipt yarating va submit qiling**
   - Item A: 100 dona, 50 USD/dona

2. **Purchase Invoice yarating (PR dan)**
   - Item A: 100 dona, 60 USD/dona
   - `Update Stock` ni yoqing
   - Submit qiling

3. **Avtomatik Natija:**
   - LCV yaratiladi: 1000 USD variance (10 USD × 100)
   - Item A tannarxi yangilanadi
   - UI da batafsil xabar ko'rsatiladi

### Multi-PR Scenario:

**Purchase Invoice:**
- Item A from PR-001: variance +500 USD
- Item B from PR-002: variance +300 USD

**Natija:**
- LCV-001 yaratiladi (PR-001 uchun) - 500 USD
- LCV-002 yaratiladi (PR-002 uchun) - 300 USD

## 🔧 Texnik Detallar

### File Structure:
```
apps/premierprint/
├── premierprint/
│   ├── doctype/
│   │   └── purchase_invoice.py     # Main logic
│   ├── setup/
│   │   └── custom_fields.py        # Setup script
│   └── hooks.py                    # Event hooks
```

### Hooks Configuration:
```python
doc_events = {
    "Purchase Invoice": {
        "on_submit": [
            "premierprint.doctype.purchase_invoice.auto_create_lcv_for_price_variance"
        ],
        "on_cancel": "premierprint.doctype.purchase_invoice.cancel_linked_lcvs"
    }
}
```

### Asosiy Functions:

#### `auto_create_lcv_for_price_variance(doc, method)`
- Main hook function
- PI submit da chaqiriladi
- Narx farqini aniqlaydi va LCV yaratadi

#### `cancel_linked_lcvs(doc, method)`
- Cancel hook function
- PI cancel da chaqiriladi
- Linked LCV larni cancel qiladi

#### `analyze_and_group_items_by_pr(doc)`
- Itemlarni PR bo'yicha guruhlaydi
- Har bir item uchun variance hisoblab beradi

#### `create_lcv_for_pr_group(doc, pr_name, pr_group_data)`
- Bitta PR uchun LCV yaratadi
- Item-specific distribution qo'llaydi

## 💡 Muhim Eslatmalar

### ✅ LCV Yaratiladi:
- `update_stock = True` bo'lgan PI lar uchun
- PR reference bor itemlar uchun
- Narx farqi > 0.01 bo'lsa

### ❌ LCV Yaratilmaydi:
- `update_stock = False` bo'lsa
- Return invoice bo'lsa (`is_return = True`)
- PR reference yo'q bo'lsa
- Narx farqi juda kichik bo'lsa (< 0.01)
- Allaqachon LCV yaratilgan bo'lsa

## 🔍 Muammolarni Tuzatish (Troubleshooting)

### 1. LCV yaratilmadi?

**Tekshirish:**
```bash
# Error Log
bench --site [site] mariadb
# MariaDB da:
SELECT * FROM `tabError Log` WHERE title LIKE '%Auto LCV Failed%' ORDER BY creation DESC LIMIT 5;
```

**Umumiy sabablar:**
- `update_stock` yoqilmagandir
- PR reference yo'q
- Narx farqi yo'q yoki juda kichik
- Permission muammosi

### 2. Currency conversion noto'g'ri?

**Tekshirish:**
- Purchase Invoice da `conversion_rate` to'g'ri to'ldirilganligini tekshiring
- Currency Exchange settings ni ko'ring

### 3. Custom Field topilmadi?

```bash
# Custom field borligini tekshirish
bench --site [site] console

# Console da:
import frappe
frappe.db.exists("Custom Field", "Purchase Invoice-custom_price_variance_lcvs")
# True qaytishi kerak
```

## 📈 Performance

- **Item Matching**: O(n) - har bir PI item uchun 1-2 ta DB query
- **LCV Creation**: PR soni bo'yicha (har bir PR uchun alohida LCV)
- **Memory**: Minimal - faqat zarur data xotiraga yuklanadi

## 🔐 Security & Permissions

- LCV creation `ignore_permissions=True` bilan ishlaydi
- Faqat submitted PI lar uchun ishlayd
- Cancel faqat submitted LCV lar uchun

## 🧪 Testing Checklist

- [ ] Oddiy PI + PR (1 item, narx farqi bor)
- [ ] Multi-item PI (ba'zilarida farq bor, ba'zilarida yo'q)
- [ ] Multi-PR PI (har bir PR uchun alohida LCV)
- [ ] Currency conversion (UZS → USD)
- [ ] Cancel PI → LCV cancel bo'lishi
- [ ] Duplicate prevention (qayta submit)
- [ ] Return invoice (LCV yaratilmasligi)

## 📞 Support

Muammo yoki savol bo'lsa:
1. Error Log ni tekshiring
2. Console da manual test qiling
3. Custom Field mavjudligini tekshiring

---

**Version**: 1.0
**Last Updated**: 2025-12-25
**Author**: Professional Development Team
