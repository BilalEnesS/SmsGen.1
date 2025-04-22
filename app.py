from flask import Flask, render_template, request, jsonify
import requests
from bs4 import BeautifulSoup
import openai
from urllib.parse import urljoin
from datetime import datetime
import instaloader
from dotenv import load_dotenv
import os
import re


#ortalama bir istek 0.15dolar-> 0.5 Tl
app = Flask(__name__)

openai.api_key = "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"
def get_brand_info(url):
    """Web sitesinden marka bilgilerini çeker."""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code != 200:
            return {"Hata": "Siteye erişilemedi."}

        soup = BeautifulSoup(response.text, "html.parser")

        def clean_brand_name(title):
            """Başlıktan marka adını temizler, örneğin 'Ajans360 - Dijital Ajans' -> 'Ajans360' """
            if not title:
                return ""
            return re.split(r"[-|•|:]", title)[0].strip()

        raw_title = soup.title.string if soup.title else "Marka adı bulunamadı."
        brand_name = clean_brand_name(raw_title)

        meta_desc = soup.find("meta", attrs={"name": "description"})
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        h1_tag = soup.find("h1")
        p_tag = soup.find("p")

        about_url = None
        for link in soup.find_all("a", href=True):
            href = link["href"].lower()
            if "about" in href or "hakkimizda" in href or "kurumsal" in href:
                about_url = urljoin(url, link["href"])
                break

        about_text = ""
        if about_url:
            about_response = requests.get(about_url, headers=headers, timeout=10)
            if about_response.status_code == 200:
                about_soup = BeautifulSoup(about_response.text, "html.parser")
                about_paragraphs = about_soup.find_all("p")
                about_text = " ".join(p.get_text(strip=True) for p in about_paragraphs[:5])

        data = {
            "Marka Adı": brand_name.strip() if brand_name else "",
            "Meta Açıklaması": meta_desc["content"].strip() if meta_desc and meta_desc.get("content") else "",
            "OG Açıklaması": og_desc["content"].strip() if og_desc and og_desc.get("content") else "",
            "Ana Başlık (H1)": h1_tag.get_text(strip=True) if h1_tag else "",
            "İlk Paragraf": p_tag.get_text(strip=True) if p_tag else "",
            "Hakkımızda İçerik": about_text
        }

        return data

    except Exception as e:
        return {"Hata": str(e)}

def summarize_with_gpt(data):
    """GPT ile marka hakkında özet oluşturur."""
    try:
        prompt_text = f"""
        Aşağıda bir markaya ait web sitesinden alınan çeşitli bilgileri bulacaksınız. 
        Lütfen bu bilgileri kullanarak markanın ne yaptığını anlatan kısa bir özet verin.

        Marka Adı: {data.get("Marka Adı", "")}
        Meta Açıklaması: {data.get("Meta Açıklaması", "")}
        OG Açıklaması: {data.get("OG Açıklaması", "")}
        Ana Başlık (H1): {data.get("Ana Başlık (H1)", "")}
        İlk Paragraf: {data.get("İlk Paragraf", "")}
        Hakkımızda İçerik: {data.get("Hakkımızda İçerik", "")}

        Özet:
        """

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Sen bir içerik özetleyicisin. Maximum 200 karakterle özetle."},
                {"role": "user", "content": prompt_text}
            ],
            max_tokens=200
        )

        return response["choices"][0]["message"]["content"].strip()

    except Exception as e:
        return f"Hata oluştu: {e}"

def generate_sms_ads(summary, brand_name, campaign_info):
    """GPT ile 3 farklı SMS reklamı önerisi oluşturur."""
    try:
        # Gelen kampanya bilgilerini ayıklama
        discount_rate = campaign_info.get("discount_rate", "")
        campaign_details = campaign_info.get("campaign_details", "")
        message_tone = campaign_info.get("message_tone", "")
        start_date = campaign_info.get("start_date", "")
        end_date = campaign_info.get("end_date", "")
        address = campaign_info.get("address", "")
        contact = campaign_info.get("contact", "")
        
        # Tarih formatını düzenleme
        date_info = f"{start_date} - {end_date}"
        
        # Maksimum karakter sayısı (2 SMS = 310 karakter)
        max_chars = 310
        
        # SMS şablonu ve zorunlu bilgiler
        mandatory_text = f"{brand_name}'den Turkcell'lilere özel %{discount_rate} indirim! {date_info}. {address}. İletişim: {contact}"
        remaining_chars = max_chars - len(mandatory_text) - 20  # 20 karakter buffer
        
        prompt_text = f"""
        Aşağıda bir markanın kısa bir özeti bulunmaktadır. İndirim kampanyası için
        TAM OLARAK 3 ADET SMS reklamı önerisi oluştur.
        
        Marka: {brand_name}
        Marka Özeti: {summary}
        Kampanya Detayı: {campaign_details}
        
        ÖNEMLİ KURALLAR:
        1. Her SMS'in başında mutlaka "{brand_name}'den Turkcell'lilere özel %{discount_rate} indirim!" ifadesi kullanılmalı. 
        2. Her SMS'in sonunda kampanya tarihi "{date_info}", adres "{address}" ve iletişim "{contact}" bilgisi yer almalı. 2025.02.26 ya da 2025-03-03 görünümü şeklinde değil 03 şubat gibi yazılmalı tarih.
        3. Kampanya detayında belirtilen bilgileri SMS'lerde kullan ve vurgula
        4. Mesaj tonu: {message_tone}
        5. Maksimum karakter sayısı: {max_chars} karakter (2 SMS)
        6. Mesaj içeriği için kullanabileceğin karakter sayısı: {remaining_chars}
        7. Tam olarak 3 farklı SMS önerisi sunulmalıdır
        8. Markanın adı Türkcell değil doğru kullanımı Turkcell olmalı her zaman.
        9. Hiçbir SMS, "Heyy!", "Vay!", "Harika!" gibi ünlem içeren ifadelerle başlamamalıdır. 
        10.İletişim:"{contact}" şeklinde numarayı yazmalısın.
        
        Lütfen her SMS'i "ÖNERİ 1:", "ÖNERİ 2:", "ÖNERİ 3:" şeklinde numaralandır ve her önerinin altında karakter sayısını belirt. Buradaki karakter sayılarına boşlukları ve noktalama işaretleni de ekleyerek say. Asla 310 karakterden fazla karakterle sms üretme.
        """

        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Sen bir kreatif reklam metni yazarısın. {message_tone} bir dil kullan ve karakter sınırına kesinlikle uy. Tam olarak 3 farklı SMS önerisi sun."},
                {"role": "user", "content": prompt_text}
            ],
            max_tokens=500
        )

        return response["choices"][0]["message"]["content"].strip()

    except Exception as e:
        return f"Hata oluştu: {e}"

def get_instagram_profile_info(username):
    """Instagram profilinden marka bilgilerini çeker."""
    try:
        # Instaloader nesnesini oluştur
        L = instaloader.Instaloader()
        
        # Profil bilgilerini al
        profile = instaloader.Profile.from_username(L.context, username)
        
        data = {
            "Marka Adı": profile.full_name,
            "Meta Açıklaması": profile.biography,
            "OG Açıklaması": profile.biography,
            "Ana Başlık (H1)": profile.full_name,
            "İlk Paragraf": profile.biography,
            "Hakkımızda İçerik": profile.biography
        }

        return data

    except Exception as e:
        return {"Hata": str(e)}

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        # Form verilerini al
        form_data = request.form.to_dict()
        data_source = form_data.get("data_source", "url")
        
        # Marka bilgileri ve özet
        brand_data = {}
        summary = ""
        brand_name = ""
        
        if data_source == "instagram":
            username = form_data.get("instagram_username", "")
            brand_data = get_instagram_profile_info(username)
            summary = summarize_with_gpt(brand_data)
            brand_name = brand_data.get("Marka Adı", "")
        elif data_source == "url":
            url = form_data.get("url", "")
            brand_data = get_brand_info(url)
            summary = summarize_with_gpt(brand_data)
            brand_name = brand_data.get("Marka Adı", "")
        else:
            brand_name = form_data.get("manual_brand_name", "")
            manual_description = form_data.get("manual_description", "")
            brand_data = {
                "Marka Adı": brand_name,
                "Manuel Açıklama": manual_description
            }
            summary = manual_description
        
        # Kampanya bilgilerini al
        campaign_info = {
            "discount_rate": form_data.get("discount_rate", ""),
            "campaign_details": form_data.get("campaign_details", ""),
            "message_tone": form_data.get("message_tone", ""),
            "start_date": form_data.get("start_date", ""),
            "end_date": form_data.get("end_date", ""),
            "address": form_data.get("address", ""),
            "contact": form_data.get("contact", "")
        }
        
        # 3 Farklı SMS reklamı önerisi oluştur
        sms_ads = generate_sms_ads(summary, brand_name, campaign_info)
        
        return jsonify({
            "data": brand_data, 
            "summary": summary, 
            "sms_ads": sms_ads,
            "campaign_info": campaign_info
        })

    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
