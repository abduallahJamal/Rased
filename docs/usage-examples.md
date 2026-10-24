<div align="right" dir="rtl">

# أمثلة الاستخدام ومسارات الاستطلاع الأمني — Rased (`راصد`)

**[🇬🇧 English Version](usage-examples.en.md)** · **[⬅ العودة إلى التوثيق العربي](../README.ar.md)**

---

## ١. الربط المباشر مع أدوات اكتشاف النطاقات (`subfinder` ← `httpx` ← `rased`)

مرّر النطاقات الحيّة مباشرةً إلى `rased` لالتقاط ملفات تطبيقات الويب الحديث (SPA) مع استبعاد الصور والخطوط الثقيلة:

</div>

```bash
subfinder -d example.com -silent \
  | httpx -silent \
  | rased -c 5 -d 250 --no-third-party --exclude "image/" --exclude "font/" -o recon-example -v
```

<div align="right" dir="rtl">

---

## ٢. جمع حزم JavaScript لتحليل نقاط النهاية (API Endpoints)

اجمع ملفات JavaScript الخاصة بالنطاق المستهدف فقط ثم ابحث بداخلها عن المسارات المخفية ومتغيرات البيئة:

</div>

```bash
rased -f targets.txt --no-third-party --include ".js" --include "javascript" -o js-mirror
rg -n "(api/v[0-9]+|graphql|Bearer |NEXT_PUBLIC_)" js-mirror/
```

<div align="right" dir="rtl">

---

## ٣. مراجعة ترويسات الأمان (`CSP` و`HSTS`) عبر ملفات `.meta`

بما أن كل ملف محفوظ يرافقه ملف `.meta` بصيغة JSON، يمكنك فحص غياب ترويسات الأمان بسهولة عبر `jq`:

</div>

```bash
echo "https://example.com" | rased -o audit --no-third-party
jq -r 'select(.response.headers["content-security-policy"] == null) | .url' audit/**/*.meta
```

<div align="right" dir="rtl">

---

## ٤. تغذية خريطة المواقع في Burp Suite وOWASP ZAP تلقائياً

شغّل متصفح Chromium عبر بروكسي الاعتراض المحلي لتعبئة خريطة الهدف بجميع طلبات XHR/fetch الحقيقية:

</div>

```bash
rased -f scope-urls.txt -c 3 -d 400 -p http://127.0.0.1:8080 -k -o burp-session
```

<div align="right" dir="rtl">

---

## ٥. جرد سلاسل التوريد والمكتبات الخارجية (`--third-party`)

احصر جميع شبكات الـ CDN وسكربتات الطرف الثالث التي تحمّلها تطبيقاتك في بيئة الإنتاج:

</div>

```bash
rased -f production-apps.txt --third-party -o thirdparty-audit -v
```

<div align="right" dir="rtl">

---

## ٦. تشغيل لوحة التحكم التفاعلية (`rased-dashboard`)

شغّل واجهة الويب التفاعلية محلياً لاستعراض الأصول وتجربة تعبيرات JavaScript بصرياً:

</div>

```bash
PORT=8787 rased-dashboard
```
