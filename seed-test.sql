INSERT INTO pages (slug, engine, category, title, description, config, content, faqs, schema_json, status, published_at) VALUES (
  'tip-calculator',
  'calculator',
  'finance',
  'Tip Calculator | Free Gratuity & Bill Splitter',
  'Calculate tips instantly. Choose your percentage, split the bill, and round up — the fastest free tip calculator online.',
  '{
    "inputs": [
      {"id": "bill", "label": "Bill Amount", "type": "number", "prefix": "$", "default": 50, "min": 0, "step": 0.01},
      {"id": "tipPct", "label": "Tip Percentage", "type": "preset", "suffix": "%", "default": 18, "options": [10, 15, 18, 20, 25]},
      {"id": "people", "label": "Split Between", "type": "number", "default": 1, "min": 1, "step": 1}
    ],
    "outputs": [
      {"id": "tip", "label": "Tip Amount", "format": "currency"},
      {"id": "total", "label": "Total", "format": "currency"},
      {"id": "perPerson", "label": "Per Person", "format": "currency"}
    ],
    "formula": "var tip = bill * tipPct / 100; var total = bill + tip; var perPerson = total / people",
    "verdicts": [
      {"max": 10, "label": "Below Standard", "color": "red"},
      {"max": 15, "label": "Standard", "color": "yellow"},
      {"max": 20, "label": "Good", "color": "green"},
      {"max": 25, "label": "Generous", "color": "green"},
      {"max": 100, "label": "Very Generous!", "color": "blue"}
    ],
    "verdictOutput": "tipPct"
  }',
  '[
    {"heading": "How Much Should You Tip?", "body": "<p>In the United States, tipping is customary in many service industries. Here are standard tip ranges:</p><p><strong>Restaurants:</strong> 15–20% of the pre-tax bill is standard. For exceptional service, 25% or more.</p><p><strong>Delivery:</strong> 15–20%, with a minimum of $3–5 for small orders.</p><p><strong>Bars:</strong> $1–2 per drink, or 15–20% of the tab.</p><p><strong>Hair salons:</strong> 15–20% of the service cost.</p><p><strong>Rideshare:</strong> 15–20% for good service, especially for longer rides.</p>"},
    {"heading": "Tipping Etiquette by Country", "body": "<p><strong>United States & Canada:</strong> 15–20% is expected at restaurants.</p><p><strong>United Kingdom:</strong> 10–12.5% is common, often included as a service charge.</p><p><strong>Japan:</strong> Tipping is not customary and can be considered rude.</p><p><strong>Australia:</strong> Not expected, but 10% for exceptional service is appreciated.</p><p><strong>Europe:</strong> Varies by country. Rounding up the bill is common in Germany and France.</p>"},
    {"heading": "How to Calculate a Tip in Your Head", "body": "<p><strong>10% tip:</strong> Move the decimal point one place left. $45.00 → $4.50</p><p><strong>15% tip:</strong> Calculate 10%, then add half. $45.00 → $4.50 + $2.25 = $6.75</p><p><strong>20% tip:</strong> Calculate 10%, then double it. $45.00 → $4.50 × 2 = $9.00</p><p><strong>25% tip:</strong> Calculate 10%, multiply by 2.5. Or find 25% by dividing by 4.</p>"}
  ]',
  '[
    {"q": "How much should I tip at a restaurant?", "a": "The standard tip at a restaurant in the US is 15-20% of the pre-tax bill. For exceptional service, you might tip 25% or more. For poor service, 10% is the minimum."},
    {"q": "Should I tip on the pre-tax or post-tax amount?", "a": "Technically, you should tip on the pre-tax amount. However, many people tip on the total bill including tax for simplicity. The difference is usually small."},
    {"q": "How do I split a tip between multiple people?", "a": "Calculate the total bill plus tip, then divide by the number of people. Our calculator does this automatically — just enter the number of people in the split field."},
    {"q": "Is it rude not to tip?", "a": "In the US, not tipping is considered very rude as servers rely on tips for most of their income. In other countries like Japan, tipping may actually be considered rude."},
    {"q": "How much should I tip for delivery?", "a": "For food delivery, tip 15-20% with a minimum of $3-5. For large or difficult deliveries (heavy items, stairs, bad weather), consider tipping more."}
  ]',
  '{"@context":"https://schema.org","@type":"WebApplication","name":"Tip Calculator","url":"https://gab.ae/tip-calculator","description":"Calculate tips instantly. Choose your percentage, split the bill, and round up.","applicationCategory":"FinanceApplication","operatingSystem":"All","offers":{"@type":"Offer","price":"0","priceCurrency":"USD"}}',
  'live',
  '2026-03-26'
);
