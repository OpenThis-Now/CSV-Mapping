# AI Processing Optimization

## 🚀 Parallell AI-processning med flera API-nycklar

### Problem
- AI-processningen var sekventiell (en produkt i taget)
- En OpenAI API-nyckel = rate limiting begränsningar
- Långsam bearbetning av stora batchar

### Lösning
- **Parallell bearbetning:** Upp till 5 produkter processas samtidigt
- **Flera API-nycklar:** Roterar mellan 5 olika OpenAI API-nycklar
- **ThreadPoolExecutor:** Hanterar parallell bearbetning säkert

### Konfiguration

Lägg till flera OpenAI API-nycklar i din `.env` fil:

```bash
# Primär API-nyckel
OPENAI_API_KEY=sk-your-first-api-key-here

# Ytterligare API-nycklar för parallell bearbetning
OPENAI_API_KEY_2=sk-your-second-api-key-here
OPENAI_API_KEY_3=sk-your-third-api-key-here
OPENAI_API_KEY_4=sk-your-fourth-api-key-here
OPENAI_API_KEY_5=sk-your-fifth-api-key-here
```

### Prestanda

**Före optimering:**
- 1 produkt per sekund
- 10 produkter = 10 sekunder

**Efter optimering:**
- 5 produkter samtidigt
- 10 produkter = 2 sekunder (5x snabbare)

### Teknisk implementation

1. **API Key Rotation:** `api_key_index = product.customer_row_index % 5`
2. **Parallell bearbetning:** `ThreadPoolExecutor(max_workers=5)`
3. **Säker session-hantering:** Varje tråd får sin egen databas-session
4. **Felhantering:** Robust error handling per tråd

### Kostnad

- **1 API-nyckel:** $0.15 per 1M tokens (gpt-4o-mini)
- **5 API-nycklar:** Samma kostnad, men 5x snabbare bearbetning
- **Ingen extra kostnad** för parallell bearbetning

### Fallback

Om bara 1 API-nyckel finns:
- Systemet använder bara den nyckeln
- Fortfarande parallell bearbetning (men med samma rate limits)
- Automatisk fallback till tillgängliga nycklar

### Monitoring

Loggar visar:
- Vilken API-nyckel som används
- Parallell bearbetning status
- Fel per tråd
- Prestanda-mätningar
