/**
 * Seed Pages — Template-based page generator
 * Creates basic pages from keyword queue with zero LLM tokens.
 * Processes 1 keyword per cron run.
 */

const SITE_TO_APEX = {
  'westmount': 'capital-markets-wealth-guide-2026',
  'firemaths': 'capital-markets-wealth-guide-2026',
  'siliconbased': 'software-ai-infrastructure-guide-2026',
  'fixitwithducttape': 'software-ai-infrastructure-guide-2026',
  'leeroyjenkins': 'digital-media-creator-economy-guide-2026',
  'bodycount': 'human-optimization-health-guide-2026',
  '28grams': 'fine-arts-design-creative-guide-2026',
  'migratingmammals': 'global-mobility-geo-arbitrage-guide-2026',
  'sendnerds': 'education-knowledge-commerce-guide-2026',
  'getthebag': 'ecommerce-supply-chain-guide-2026',
  'pleasestartplease': 'ecommerce-supply-chain-guide-2026',
  'nookienook': 'interpersonal-dynamics-intimacy-guide-2026',
  'ijustwantto': 'real-estate-hospitality-guide-2026',
  'eeniemeenie': 'digital-media-creator-economy-guide-2026',
  'papyruspeople': 'digital-media-creator-economy-guide-2026',
  'justonemoment': 'digital-media-creator-economy-guide-2026',
};

const APEX_NAMES = {
  'capital-markets-wealth-guide-2026': 'Capital Markets & Wealth Guide',
  'software-ai-infrastructure-guide-2026': 'Software & AI Infrastructure Guide',
  'digital-media-creator-economy-guide-2026': 'Digital Media & Creator Economy Guide',
  'human-optimization-health-guide-2026': 'Human Optimization & Health Guide',
  'fine-arts-design-creative-guide-2026': 'Fine Arts, Design & Creative Guide',
  'global-mobility-geo-arbitrage-guide-2026': 'Global Mobility & Geo-Arbitrage Guide',
  'education-knowledge-commerce-guide-2026': 'Education & Knowledge Commerce Guide',
  'ecommerce-supply-chain-guide-2026': 'E-Commerce & Supply Chain Guide',
  'interpersonal-dynamics-intimacy-guide-2026': 'Interpersonal Dynamics & Intimacy Guide',
  'real-estate-hospitality-guide-2026': 'Real Estate & Hospitality Guide',
};

// Site-to-category mapping for pages table
const SITE_TO_CATEGORY = {
  'westmount': 'finance',
  'firemaths': 'finance',
  'siliconbased': 'tech',
  'fixitwithducttape': 'tech',
  'leeroyjenkins': 'gaming',
  'bodycount': 'health',
  '28grams': 'food',
  'migratingmammals': 'lifestyle',
  'sendnerds': 'education',
  'getthebag': 'lifestyle',
  'pleasestartplease': 'auto',
  'nookienook': 'health',
  'ijustwantto': 'lifestyle',
  'eeniemeenie': 'tools',
  'papyruspeople': 'tools',
  'justonemoment': 'tools',
};

const SEED_CSS = `
<style>
.seed-page { max-width: 780px; margin: 0 auto; padding: 1.5rem 1rem; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; color: #e2e8f0; }
.seed-page h1 { font-size: 1.75rem; font-weight: 800; color: #fff; margin-bottom: 0.5rem; line-height: 1.2; }
.seed-meta { font-size: 0.8rem; color: #64748b; margin-bottom: 2rem; }
.seed-section { background: #12121a; border: 1px solid #1e1e2e; border-radius: 12px; padding: 1.25rem 1.5rem; margin-bottom: 1rem; }
.seed-section h2 { font-size: 1.15rem; font-weight: 700; color: #818cf8; margin-bottom: 0.75rem; }
.seed-section h3 { font-size: 1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 0.5rem; }
.seed-section p { font-size: 0.95rem; line-height: 1.7; color: #94a3b8; margin-bottom: 0.5rem; }
.seed-section ul, .seed-section ol { padding-left: 1.25rem; color: #94a3b8; font-size: 0.95rem; line-height: 1.8; }
.seed-section li { margin-bottom: 0.25rem; }
.seed-section .faq-item { border-top: 1px solid #1e1e2e; padding-top: 0.75rem; margin-top: 0.75rem; }
.seed-section .faq-item:first-child { border-top: none; padding-top: 0; margin-top: 0; }
.seed-explore { text-align: center; margin-top: 1.5rem; font-size: 0.85rem; color: #64748b; }
.seed-explore a { color: #818cf8; text-decoration: underline; }
.seed-calc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin: 1rem 0; }
.seed-calc-input, .seed-calc-output { background: #0a0a0a; border: 1px solid #1e1e2e; border-radius: 8px; padding: 0.75rem; }
.seed-calc-input label, .seed-calc-output label { display: block; font-size: 0.8rem; color: #64748b; margin-bottom: 0.25rem; }
.seed-calc-input input { width: 100%; background: transparent; border: none; color: #fff; font-size: 1.1rem; outline: none; }
.seed-calc-output .value { font-size: 1.3rem; font-weight: 700; color: #818cf8; }
.seed-compare-table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }
.seed-compare-table th, .seed-compare-table td { padding: 0.6rem 0.75rem; text-align: left; border-bottom: 1px solid #1e1e2e; }
.seed-compare-table th { color: #818cf8; font-weight: 600; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; }
.seed-compare-table td { color: #94a3b8; }
@media (max-width: 640px) {
  .seed-page h1 { font-size: 1.35rem; }
  .seed-calc-grid { grid-template-columns: 1fr; }
  .seed-compare-table { font-size: 0.8rem; }
  .seed-compare-table th, .seed-compare-table td { padding: 0.4rem 0.5rem; }
}
</style>`;

const ACRONYMS = ['ETF', 'REIT', 'IRA', '401k', 'FIRE', 'CEO', 'IPO', 'AI', 'API', 'SEO', 'CSS', 'HTML', 'NFT', 'GPU', 'CPU', 'DIY', 'HIIT', 'BMI', 'HPV', 'IUD', 'HVAC', 'ROI', 'DPI', 'FPS'];

function titleCase(str) {
  if (!str) return '';
  let cased = str.replace(/\b\w/g, c => c.toUpperCase());
  ACRONYMS.forEach(acc => {
    cased = cased.replace(new RegExp(`\\b${acc}\\b`, 'gi'), acc);
  });
  return cased;
}

function esc(str) {
  return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function getMonthYear() {
  const d = new Date();
  const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  return { month: months[d.getMonth()], year: d.getFullYear() };
}

const CATEGORY_DESCRIPTORS = {
  finance: [
    "Known for consistently low expense ratios and strong fee structures",
    "Offers the highest historical dividend yield in its specific category",
    "Best overall option for beginners with zero minimum investment required",
    "Top consistent performer over the trailing 5-year and 10-year periods",
    "Most extensively diversified holdings across multiple global sectors",
    "Demonstrates the lowest historical volatility among its direct peers",
    "Highly optimized for tax-efficient income generation and wealth preservation",
    "Boasts the highest assets under management, making it widely trusted",
    "Features the most reliable and predictable monthly distribution schedule",
    "Maintains the strongest historical track record of consistent dividend growth"
  ],
  tech: [
    "Fully open source with an incredibly active and supportive community",
    "Features the most comprehensive documentation and beginner tutorials",
    "Consistently clocks the fastest performance in independent benchmarks",
    "Offers seamless integrations with the most popular enterprise tools",
    "Provides enterprise-grade security features right out of the box",
    "Known for its highly intuitive and customizable user interface",
    "Maintains the highest uptime guarantee and reliable cloud infrastructure",
    "Backed by major industry leaders and heavily adopted by Fortune 500s",
    "Releases the most frequent feature updates and bug fixes",
    "Best scalable architecture designed specifically for high-growth startups"
  ],
  health: [
    "Extensively backed by rigorous peer-reviewed clinical research",
    "Most highly recommended by certified medical professionals and specialists",
    "Formulated exclusively with premium, highly bioavailable ingredients",
    "Manufactured in strict FDA-registered and cGMP-certified facilities",
    "Consistently delivers the fastest measurable results in consumer trials",
    "Best holistic option for long-term preventive health and wellness",
    "Features the cleanest ingredient profile with zero artificial additives",
    "Highly optimized for rapid absorption and maximum bodily utilization",
    "Offers the most comprehensive full-spectrum approach to wellness",
    "Most trusted brand with decades of consistent safety and efficacy data"
  ],
  gaming: [
    "Widely considered the absolute best value for money in its price tier",
    "Top-rated and consistently used by professional esports athletes",
    "Features the lowest latency and highest polling rates available",
    "Boasts industry-leading build quality and long-term durability",
    "Offers the most immersive and high-fidelity sensory experience",
    "Highly customizable with extensive software and hardware macro support",
    "Designed with superior ergonomics for marathon gaming sessions",
    "Features best-in-class battery life and reliable wireless connectivity",
    "Provides the most accurate tracking and precision sensors on the market",
    "Maintains the strongest backward compatibility and cross-platform support"
  ],
  lifestyle: [ // combining home/diy/lifestyle
    "Renowned for being the most durable and long-lasting in its class",
    "Incredibly easy to install and set up, even for complete beginners",
    "Features the most elegant, modern, and aesthetically pleasing design",
    "Highly versatile and easily adaptable to multiple different use cases",
    "Crafted from premium, sustainably sourced, and eco-friendly materials",
    "Offers the absolute best warranty and reliable customer support",
    "Consistently rated as the most space-efficient and compact solution",
    "Provides professional-grade quality at a fraction of the cost",
    "Known for its highly innovative and patented smart features",
    "The ultimate time-saving tool that dramatically streamlines daily tasks"
  ],
  food: [
    "Consistently rated as having the best overall flavor profile in blind taste tests",
    "Incredibly versatile and easily incorporated into a wide variety of recipes",
    "Sourced entirely from premium, organic, and locally sustained farms",
    "Offers the highest nutritional density and clean macronutrient profile",
    "Features the most authentic and culturally accurate preparation methods",
    "Highly praised for its perfect texture and mouthfeel",
    "The absolute best option for individuals with specific dietary restrictions",
    "Provides exceptional shelf life without relying on artificial preservatives",
    "Known for its rich, bold, and highly complex aromatic qualities",
    "The most cost-effective bulk option for large-scale meal prep"
  ],
  travel: [
    "Unquestionably the best overall value for budget-conscious travelers",
    "Highly renowned as the most scenic and Instagram-worthy destination",
    "Offers the most deeply immersive and authentic cultural experiences",
    "Features world-class luxury accommodations and premium amenities",
    "Considered the safest and most family-friendly option in the region",
    "Boasts the most convenient access to major transit hubs and attractions",
    "The absolute best location for thrilling outdoor adventure and recreation",
    "Known for its vibrant, world-renowned culinary and nightlife scene",
    "Provides the most relaxing, secluded, and peaceful environment",
    "Highly praised for its exceptionally warm and welcoming local hospitality"
  ],
  education: [
    "Consistently the highest-rated program by enrolled students and alumni",
    "Features the most comprehensive, up-to-date, and rigorous curriculum",
    "Taught exclusively by industry-leading experts and seasoned professionals",
    "Offers the most flexible, self-paced scheduling for busy individuals",
    "Boasts the highest post-graduation job placement and success rate",
    "Provides highly interactive, hands-on projects and real-world case studies",
    "Includes unparalleled access to 1-on-1 mentorship and career coaching",
    "The most universally recognized and heavily accredited certification available",
    "Features a highly supportive, engaging, and active alumni community",
    "The absolute best return on investment for long-term career advancement"
  ],
  auto: [
    "Widely recognized for having the absolute best long-term reliability rating",
    "Features the most advanced and comprehensive standard safety suite",
    "Offers industry-leading fuel efficiency and incredibly low running costs",
    "Boasts the highest resale value retention over a 5-year ownership period",
    "Provides the most luxurious, quiet, and refined interior cabin experience",
    "Known for its exceptionally engaging and sporty driving dynamics",
    "Features the most intuitive and responsive infotainment technology",
    "The most practical and spacious option for large families and cargo",
    "Highly praised for its robust off-road capability and towing capacity",
    "Offers the most comprehensive and generous manufacturer warranty"
  ],
  tools: [
    "Universally praised as the most powerful and efficient tool in its class",
    "Features an incredibly compact, lightweight, and ergonomic design",
    "Built with industrial-grade materials for maximum lifespan under heavy use",
    "Offers the longest continuous runtime and fastest battery charging",
    "The most versatile multi-tool capable of replacing several standalone devices",
    "Known for absolute precision, accuracy, and consistent performance",
    "Highly intuitive to use with virtually no learning curve for beginners",
    "Provides the best dust management and safety mechanisms available",
    "Backed by the most responsive and helpful professional customer service",
    "The absolute best budget-friendly alternative to expensive flagship brands"
  ],
  default: [
    "Consistently ranks as the most popular and widely adopted option",
    "Offers an incredibly strong balance of performance and affordability",
    "Highly praised for its exceptional reliability and long-term durability",
    "Features the most user-friendly design and straightforward setup process",
    "Provides the most comprehensive and valuable core feature set",
    "Backed by overwhelming positive sentiment in expert and user reviews",
    "Considered the absolute safest and most trustworthy choice on the market",
    "Delivers the most consistent and high-quality results across the board",
    "Highly adaptable and easily scales to meet growing demands",
    "Unquestionably the best all-around value for the vast majority of users"
  ]
};

const LISTICLE_STRUCTURES = [
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — ${desc}. This makes it a standout choice for ${esc(pk)} enthusiasts looking for quality.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — When it comes to ${esc(pk)}, this option is ${desc.toLowerCase()}, earning it a top spot on our list.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — A highly regarded solution for ${esc(pk)}. It is ${desc.toLowerCase()}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — If you need reliable ${esc(pk)}, consider this. ${desc}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — ${desc}. Many users prefer this specific route for their ${esc(pk)} needs.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — Taking a unique approach to ${esc(pk)}, this option is ${desc.toLowerCase()}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — ${desc}. It consistently over-delivers for anyone researching ${esc(pk)}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — For those prioritizing excellence in ${esc(pk)}, this is ${desc.toLowerCase()}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — Recognized widely for ${esc(pk)}, this pick is ${desc.toLowerCase()}.</li>`,
  (n, pk, desc) => `<li><strong>Option ${n}</strong> — ${desc}. A rock-solid contender in the ${esc(pk)} space.</li>`
];

const EDUCATIONAL_CONTENT = {
  finance: {
    what: "A {keyword} is a foundational financial concept that plays a critical role in strategic capital allocation and wealth preservation. Investors use them to mitigate risk, optimize their portfolios, and ensure long-term stability in volatile markets. The market for {keyword} has grown significantly, with increasing institutional adoption and regulatory clarity driving mainstream interest.",
    how: "The mechanics of {keyword} involve complex interplay between market forces, economic indicators, and investor sentiment. Key factors include prevailing interest rates, inflation expectations, and macroeconomic policy shifts. Most experts recommend approaching {keyword} with a diversified strategy and a long-term perspective.",
    facts: [
      "Historically provides a reliable hedge against broader market downturns.",
      "Often heavily influenced by central bank policy and interest rate adjustments.",
      "Tax implications can vary significantly depending on the holding period and jurisdiction.",
      "Considered a core component of modern portfolio theory and asset allocation."
    ]
  },
  tech: {
    what: "A {keyword} is an essential tool in the modern technology ecosystem, enabling users and organizations to build, scale, and optimize operations. Enthusiasts and professionals use them to streamline workflows, enhance digital experiences, and accelerate time-to-value. The market for {keyword} has grown significantly, with rapid innovation driving ongoing demand.",
    how: "The mechanics of {keyword} involve core computational functions, system compatibility, and hardware or software integrations. Key factors include processing efficiency, interface intuitiveness, and overall reliability. Most experts recommend evaluating {keyword} based on the specific requirements of your intended environment.",
    facts: [
      "Performance and utility often scale linearly with quality and component selection.",
      "Regular updates and patches are crucial for maintaining security and functionality.",
      "Interoperability with existing tools and platforms heavily influences adoption.",
      "Community support and comprehensive documentation provide significant long-term value."
    ],
    faq1: "The best {keyword} seamlessly integrates into your existing workflow or setup, providing robust performance without an unnecessarily steep learning curve. Key features like reliability and active developer support are crucial.",
    faq2: "Understanding {keyword} is important because it allows you to optimize your technological footprint. Making an informed decision prevents workflow bottlenecks and ensures long-term compatibility."
  },
  health: {
    what: "A {keyword} is a key element of comprehensive human optimization and preventative health protocols. Medical professionals and individuals use them to improve baseline biomarkers, enhance recovery, and maximize overall longevity. The market for {keyword} has grown significantly, with cutting-edge clinical research validating long-held hypotheses about human physiology.",
    how: "The mechanics of {keyword} involve complex biochemical pathways, systemic inflammatory responses, and cellular metabolic function. Key factors include individual genetic predispositions, environmental stressors, and dietary consistency. Most experts recommend approaching {keyword} as part of a holistic lifestyle intervention rather than a standalone cure.",
    facts: [
      "Efficacy is highly dependent on consistent adherence and proper dosage protocols.",
      "Often interacts synergistically with other dietary or pharmacological interventions.",
      "Clinical outcomes can vary widely based on baseline metabolic health.",
      "Safety profiles are established through rigorous, long-term peer-reviewed studies."
    ],
    faq1: "When considering {keyword}, the best options prioritize high-quality ingredients, proven efficacy, and excellent safety profiles. It's important to consult with professionals to find the right fit for your body.",
    faq2: "Understanding the role of {keyword} allows you to take a proactive approach to your personal health. This knowledge helps you optimize recovery and long-term well-being."
  },
  food: {
    what: "A {keyword} is a fundamental component of culinary science, providing the necessary flavor profile, texture, and structural integrity to complex dishes. Chefs and home cooks use them to elevate traditional recipes, balance macronutrients, and create unique gastronomic experiences. The market for {keyword} has grown significantly, with a renewed focus on organic sourcing and sustainable agriculture.",
    how: "The mechanics of {keyword} involve precise temperature control, chemical reactions like the Maillard response, and accurate hydration ratios. Key factors include ingredient freshness, preparation technique, and environmental humidity. Most experts recommend sourcing the highest quality {keyword} available to ensure the best possible end result.",
    facts: [
      "Flavor compounds can degrade rapidly if improperly stored or exposed to light.",
      "Preparation methods significantly alter the bioavailability of specific nutrients.",
      "Often serves as an emulsifier or stabilizing agent in complex recipes.",
      "Sourcing origin heavily dictates the final aromatic and flavor characteristics."
    ],
    faq1: "The best {keyword} will depend on your desired flavor profile, dietary needs, and recipe requirements. Premium sourcing and freshness often make the most noticeable difference in the final product.",
    faq2: "Knowing how to utilize {keyword} empowers you to elevate everyday meals into exceptional experiences. It provides the foundation for creating balanced, flavorful dishes."
  },
  travel: {
    what: "A {keyword} is a popular travel destination or service that provides unique experiences, accommodations, and transit options. Travelers use them to plan memorable trips, explore new cultures, and optimize their itineraries. The market for {keyword} has evolved, with a growing emphasis on sustainable tourism and authentic local experiences.",
    how: "Planning around a {keyword} involves coordinating logistics, comparing seasonal rates, and researching local customs. Key factors include proximity to major attractions, overall safety, and available amenities. Experts recommend thoroughly reviewing {keyword} options before booking to ensure they align with your travel style.",
    facts: [
      "Off-peak seasons often provide the best value and fewer crowds.",
      "Local regulations and visa requirements can impact your itinerary significantly.",
      "Early booking typically secures better rates and availability.",
      "Sustainable and eco-friendly options are increasingly prioritized by modern travelers."
    ],
    faq1: "The best {keyword} will depend heavily on your personal travel goals, budget, and group size. Look for options that offer a good balance of convenience, cultural immersion, and value.",
    faq2: "Researching {keyword} is important because it ensures you maximize your time and budget while traveling. Proper planning helps avoid common tourist pitfalls and enhances the overall experience."
  },
  gaming: {
    what: "A {keyword} is a critical element of the modern gaming ecosystem, directly impacting player immersion, competitive viability, and overall user experience. Enthusiasts use them to gain a competitive edge, streamline their setups, and enjoy high-fidelity digital worlds. The market for {keyword} has grown significantly, with esports and streaming pushing hardware and software limits.",
    how: "Understanding how a {keyword} works involves looking at its core design, build quality, and user-centric features. Key factors include responsiveness, ergonomics, and seamless integration with your existing setup. Most experts recommend evaluating {keyword} based on your specific playstyle and long-term comfort requirements.",
    facts: [
      "Ergonomics and physical design are often just as important as technical specifications.",
      "Customization options can dramatically alter your baseline experience.",
      "Build quality and material selection heavily influence long-term durability.",
      "Compatibility across different platforms and console generations can vary."
    ],
    faq1: "The best {keyword} will balance comfort, durability, and features tailored to your specific setup. Whether you prioritize premium materials, specialized functions, or budget-friendly value, it is important to match the product to your personal gaming habits.",
    faq2: "Choosing the right {keyword} is important because it directly affects your physical comfort and long-term enjoyment during extended sessions. The right choice minimizes fatigue and ensures a more immersive and focused experience."
  },
  lifestyle: {
    what: "A {keyword} is a practical solution for optimizing daily routines, managing physical spaces, and improving overall quality of life. Homeowners and professionals use them to increase efficiency, reduce clutter, and create a more aesthetically pleasing environment. The market for {keyword} has grown significantly, with smart-home integrations and minimalist design trends driving demand.",
    how: "The mechanics of {keyword} involve thoughtful spatial planning, durable material selection, and intuitive user design. Key factors include build quality, ease of maintenance, and long-term versatility. Most experts recommend investing in high-quality {keyword} that can adapt to changing personal needs over time.",
    facts: [
      "Longevity is largely determined by the quality of initial construction materials.",
      "Proper installation and setup are critical for maximizing functional utility.",
      "Often requires periodic maintenance to ensure optimal performance.",
      "Design trends frequently cycle, making timeless aesthetics highly desirable."
    ]
  },
  education: {
    what: "A {keyword} is an essential educational framework designed to rapidly accelerate skill acquisition and knowledge retention. Students and professionals use them to stay competitive in a rapidly evolving job market, pivot into new careers, and master complex subjects. The market for {keyword} has grown significantly, with online learning platforms democratizing access to high-level instruction.",
    how: "The mechanics of {keyword} involve structured curriculum design, active recall methodologies, and practical, hands-on application. Key factors include the quality of instruction, peer engagement, and the frequency of assessment. Most experts recommend approaching {keyword} with a disciplined, consistent study schedule.",
    facts: [
      "Retention rates improve drastically when theoretical concepts are applied practically.",
      "Mentorship and community feedback are primary drivers of long-term success.",
      "Accreditation and industry recognition vary widely between different programs.",
      "Continuous learning and adaptation are required to maintain mastery over time."
    ],
    faq1: "When choosing the best {keyword}, focus on the credibility of the instructor, the depth of the curriculum, and the applicability of the skills taught. Programs that offer hands-on projects typically provide the best value.",
    faq2: "Investing time to understand {keyword} pays dividends throughout your career. It builds a solid foundation of knowledge that can be adapted to various challenges in your professional life."
  },
  auto: {
    what: "A {keyword} is a critical component of automotive engineering, responsible for ensuring safety, efficiency, and reliable performance on the road. Drivers and mechanics use them to optimize fuel economy, enhance vehicle dynamics, and maintain long-term operational integrity. The market for {keyword} has grown significantly, with the transition to electric powertrains driving unprecedented innovation.",
    how: "The mechanics of {keyword} involve complex mechanical linkages, fluid dynamics, and sophisticated electronic control units. Key factors include material fatigue, thermal stress, and strict adherence to maintenance schedules. Most experts recommend using OEM-certified {keyword} to guarantee compatibility and prevent catastrophic failure.",
    facts: [
      "Regular preventative maintenance drastically extends the expected lifespan.",
      "Performance metrics are highly dependent on environmental operating conditions.",
      "Aftermarket modifications can inadvertently void manufacturer warranties.",
      "Safety standards and emissions regulations dictate base engineering constraints."
    ],
    faq1: "The best {keyword} for your vehicle depends entirely on the make, model, and your specific driving conditions. Always prioritize components that meet or exceed Original Equipment Manufacturer (OEM) specifications.",
    faq2: "Understanding how your {keyword} functions is vital for preventative maintenance and safety. Being informed helps you identify potential issues early and communicate effectively with mechanics."
  },
  tools: {
    what: "A {keyword} is an indispensable instrument designed to multiply human effort, enabling precision work across a wide variety of trades and disciplines. Professionals and DIY enthusiasts use them to execute complex projects, ensure structural integrity, and work more efficiently. The market for {keyword} has grown significantly, with advancements in battery technology and brushless motors leading the charge.",
    how: "The mechanics of {keyword} involve torque transfer, material hardness ratings, and ergonomic force distribution. Key factors include motor efficiency, bit or blade sharpness, and user safety mechanisms. Most experts recommend selecting {keyword} based on the specific requirements of the material being worked.",
    facts: [
      "Industrial-grade variants often feature vastly superior internal components.",
      "Battery ecosystems heavily influence long-term brand loyalty and adoption.",
      "Proper calibration and storage are essential for maintaining accurate tolerances.",
      "Safety features and vibration dampening reduce long-term occupational hazards."
    ],
    faq1: "When selecting the best {keyword}, consider the scale of your typical projects and whether you require professional-grade durability. Ergonomics, power source, and warranty should weigh heavily in your decision.",
    faq2: "Mastering the use of a {keyword} allows you to tackle projects more safely and efficiently. Proper knowledge ensures you are using the right tool for the right job, extending both the life of the tool and the quality of your work."
  },
  default: {
    what: "A {keyword} is an important solution that helps individuals and organizations achieve their goals efficiently and effectively. People rely on them to solve specific problems, streamline daily processes, and unlock new capabilities. The market for {keyword} has grown significantly, with increased awareness making it more accessible than ever.",
    how: "Understanding a {keyword} involves looking at its core components, intended use case, and practical application. Key factors include user adaptability, environmental constraints, and overall reliability. Most experts recommend a structured, methodical approach to evaluating a {keyword} to ensure it meets your specific needs.",
    facts: [
      "Consistent application and proper maintenance yield the most significant long-term results.",
      "Initial setup and familiarization are often the most crucial phases for success.",
      "Features and capabilities evolve rapidly as new methodologies are introduced.",
      "Highly adaptable depending on the specific scope and requirements of the user."
    ],
    faq1: "When looking into {keyword}, it is essential to focus on core functionality, long-term durability, and overall value. The best options consistently deliver reliable performance while remaining user-friendly.",
    faq2: "Understanding {keyword} is crucial because it allows you to make informed, practical decisions. Taking the time to research ensures you select a solution that aligns with your specific requirements and budget."
  }
};

function generateEducational(kw) {
  const { month, year } = getMonthYear();
  const pk = kw.primary_keyword;
  const pkTitle = titleCase(pk);
  const secondaries = JSON.parse(kw.secondary_keywords || '[]');
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  const category = SITE_TO_CATEGORY[kw.target_site] || 'default';
  const content = EDUCATIONAL_CONTENT[category] || EDUCATIONAL_CONTENT['default'];

  const whatText = content.what.replace(/\{keyword\}/g, pk);
  const howText = content.how.replace(/\{keyword\}/g, pk);
  const faq1Text = (content.faq1 || EDUCATIONAL_CONTENT['default'].faq1).replace(/\{keyword\}/g, pk);
  const faq2Text = (content.faq2 || EDUCATIONAL_CONTENT['default'].faq2).replace(/\{keyword\}/g, pk);

  return `${SEED_CSS}
<div class="seed-page">
  <h1>${esc(pkTitle)} — Complete Guide</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>What is ${esc(pkTitle)}?</h2>
    <p>${esc(whatText)}</p>
  </div>

  <div class="seed-section">
    <h2>Key Facts About ${esc(pkTitle)}</h2>
    <ul>
      <li>Search volume: ${(kw.total_volume || 0).toLocaleString()} searches per month</li>
      ${secondaries.length ? `<li>Related topics: ${secondaries.map(s => esc(s)).join(', ')}</li>` : ''}
      ${content.facts.map(fact => `<li>${esc(fact)}</li>`).join('\n      ')}
    </ul>
  </div>

  <div class="seed-section">
    <h2>How ${esc(pkTitle)} Works</h2>
    <p>${esc(howText)}</p>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>What is the best approach to ${esc(pk)}?</h3>
      <p>${esc(faq1Text)}</p>
    </div>
    <div class="faq-item">
      <h3>Why is ${esc(pk)} important?</h3>
      <p>${esc(faq2Text)}</p>
    </div>
  </div>

  <p class="seed-explore">Explore more: <a href="https://gab.ae/${apexSlug}">${esc(apexName)}</a></p>
</div>`;
}

function generateListicle(kw) {
  const { month, year } = getMonthYear();
  const pk = kw.primary_keyword;

  const hasPrefix = /^(best|top|how to|what is)\s/i.test(pk);
  const isBestOrTop = /^(best|top)\s/i.test(pk);

  const h1Text = hasPrefix ? `${titleCase(pk)} (${year})` : `Top 10 ${titleCase(pk)} (${year})`;

  const baseKeyword = isBestOrTop ? pk.replace(/^(best|top)\s/i, '') : pk;
  const baseKeywordTitle = titleCase(baseKeyword);

  const secondaries = JSON.parse(kw.secondary_keywords || '[]');
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  const category = SITE_TO_CATEGORY[kw.target_site] || 'default';
  const descriptors = CATEGORY_DESCRIPTORS[category] || CATEGORY_DESCRIPTORS['default'];

  const content = EDUCATIONAL_CONTENT[category] || EDUCATIONAL_CONTENT['default'];
  const faq1Text = (content.faq1 || EDUCATIONAL_CONTENT['default'].faq1).replace(/\{keyword\}/g, baseKeyword);
  const faq2Text = (content.faq2 || EDUCATIONAL_CONTENT['default'].faq2).replace(/\{keyword\}/g, baseKeyword);

  return `${SEED_CSS}
<div class="seed-page">
  <h1>${esc(h1Text)}</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>Best ${esc(baseKeywordTitle)} Overview</h2>
    <p>Looking for the best ${esc(baseKeyword)}? We've thoroughly researched and compiled the top options to help you make an informed decision. Finding the right choice can be challenging given the variety of features available, but this curated selection highlights the most highly recommended solutions in the market today.</p>
  </div>

  <div class="seed-section">
    <h2>Top 10 ${esc(baseKeywordTitle)}</h2>
    <ol>
      ${[0,1,2,3,4,5,6,7,8,9].map(i => LISTICLE_STRUCTURES[i](i + 1, baseKeyword, descriptors[i])).join('\n      ')}
    </ol>
  </div>

  <div class="seed-section">
    <h2>How We Ranked These</h2>
    <ul>
      <li>Search volume: ${(kw.total_volume || 0).toLocaleString()} searches per month</li>
      ${secondaries.length ? `<li>Related topics: ${secondaries.map(s => esc(s)).join(', ')}</li>` : ''}
      <li>Based on user reviews, expert analysis, and market data</li>
    </ul>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>What is the best ${esc(baseKeyword)}?</h3>
      <p>${esc(faq1Text)}</p>
    </div>
    <div class="faq-item">
      <h3>How do I choose the right ${esc(baseKeyword)}?</h3>
      <p>${esc(faq2Text)}</p>
    </div>
  </div>

  <p class="seed-explore">Explore more: <a href="https://gab.ae/${apexSlug}">${esc(apexName)}</a></p>
</div>`;
}

const CALCULATOR_CONTENT = {
  finance: {
    howText: "Calculating {keyword} involves aggregating specific financial variables to determine potential returns or exact costs. Input your current capital data, and the formula will instantly reflect the estimated outcome based on established financial models.",
    faqText: "To use the {keyword} calculator, input your known monetary values or rates into the fields provided. The calculator uses standard market formulas to provide a rapid, accurate estimate, helping you map out your financial strategy."
  },
  tech: {
    howText: "To calculate {keyword}, you need to quantify resource usage or system parameters. Enter your technical specifications, and the calculator will process these metrics to output an expected benchmark or cost analysis.",
    faqText: "Using the {keyword} calculator is straightforward: simply input your operational metrics or limits. It automatically computes the variables to help you provision infrastructure or estimate software requirements efficiently."
  },
  health: {
    howText: "Calculating {keyword} relies on biometric data or personal health metrics. Enter your individual stats to generate an estimate that can help guide your wellness journey or fitness protocol.",
    faqText: "Input your personal health markers into the {keyword} calculator fields. This tool uses standard physiological formulas to compute a baseline result, which you can use as a reference point for your overall health strategy."
  },
  default: {
    howText: "Understanding how to calculate {keyword} involves bringing together a few key variables. Simply enter your specific values into the calculator, and it will instantly apply standard formulas to produce a reliable result.",
    faqText: "To use this {keyword} calculator, accurately input your figures into the corresponding fields. The tool instantly runs the numbers to provide a clear, actionable result tailored to your data."
  }
};

function generateCalculator(kw) {
  const { month, year } = getMonthYear();

  const readableText = (kw.slug || '').replace(/-/g, ' ');
  const pageTypeWord = kw.page_type || 'calculator';
  const typeRegex = new RegExp('\\s+' + pageTypeWord + '$', 'i');

  const hasSuffix = typeRegex.test(readableText);
  const topic = (hasSuffix ? readableText.replace(typeRegex, '') : readableText) || kw.primary_keyword;
  const topicTitle = titleCase(topic);
  const h1Text = hasSuffix ? titleCase(readableText) : `${topicTitle} Calculator`;

  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  const category = SITE_TO_CATEGORY[kw.target_site] || 'default';
  const content = CALCULATOR_CONTENT[category] || CALCULATOR_CONTENT['default'];
  const howText = content.howText.replace(/\{keyword\}/g, topic);
  const faqText = content.faqText.replace(/\{keyword\}/g, topic);

  return `${SEED_CSS}
<div class="seed-page">
  <h1>${esc(h1Text)}</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>Calculate ${esc(topicTitle)}</h2>
    <p>Use this calculator to quickly compute ${esc(topic)}. Enter your values below for instant results.</p>
    <div class="seed-calc-grid">
      <div class="seed-calc-input">
        <label>Value A</label>
        <input type="number" id="seed-input-a" placeholder="Enter value" oninput="seedCalc()">
      </div>
      <div class="seed-calc-input">
        <label>Value B</label>
        <input type="number" id="seed-input-b" placeholder="Enter value" oninput="seedCalc()">
      </div>
      <div class="seed-calc-output">
        <label>Result</label>
        <div class="value" id="seed-result">—</div>
      </div>
    </div>
    <script>
    function seedCalc() {
      var a = parseFloat(document.getElementById('seed-input-a').value) || 0;
      var b = parseFloat(document.getElementById('seed-input-b').value) || 0;
      document.getElementById('seed-result').textContent = (a + b).toLocaleString();
    }
    </script>
  </div>

  <div class="seed-section">
    <h2>How to Calculate ${esc(topicTitle)}</h2>
    <p>${esc(howText)}</p>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>How do I use this ${esc(topic)} calculator?</h3>
      <p>${esc(faqText)}</p>
    </div>
  </div>

  <p class="seed-explore">Explore more: <a href="https://gab.ae/${apexSlug}">${esc(apexName)}</a></p>
</div>`;
}

const COMPARISON_CONTENT = {
  finance: {
    intro: "Compare the top-rated options for {keyword} side by side using our detailed evaluation matrix. See exactly how these leading financial solutions stack up against one another on critical factors such as fees, historical returns, risk profiles, and long-term value.",
    keyDiff: "Financial products often differ significantly in fee structures, tax implications, and risk thresholds. Evaluating these key differences side-by-side ensures you select an investment vehicle that aligns closely with your wealth-building strategy.",
    faqText: "The ideal {keyword} depends entirely on your specific timeline and risk tolerance. Whether you prioritize low-cost passive growth or active management, review the comparative data to find the match that aligns with your financial goals."
  },
  tech: {
    intro: "Compare the top-rated options for {keyword} side by side. See exactly how these leading solutions stack up against one another on critical factors such as integration capabilities, performance benchmarks, user popularity, and enterprise scalability.",
    keyDiff: "Software and infrastructure solutions diverge greatly regarding ease of deployment, active community support, and total cost of ownership. Evaluating these key technical differences ensures you select the most optimal stack for your operations.",
    faqText: "The ideal {keyword} ultimately depends on your technical requirements—whether you prioritize rapid deployment, extensive API access, or rock-solid security. Carefully review the matrix to find the perfect technological fit."
  },
  health: {
    intro: "Compare the top-rated options for {keyword} side by side using our detailed evaluation matrix. See exactly how these health solutions stack up against one another on critical factors such as ingredient quality, clinical backing, and overall safety.",
    keyDiff: "Health interventions and supplements often have distinct differences in bioavailability, dosage requirements, and potential side effects. Evaluating these key differences ensures you select the most effective option for your personal biology.",
    faqText: "The ideal {keyword} depends on your specific wellness goals and baseline health. Whether you prioritize organic sourcing, clinical potency, or comprehensive holistic benefits, review the data to find what works best for your body."
  },
  gaming: {
    intro: "Compare the top-rated options for {keyword} side by side. See exactly how these leading setups stack up against one another on critical factors such as ergonomics, input responsiveness, build quality, and overall immersion.",
    keyDiff: "Gaming hardware and accessories have distinct differences in tactile feedback, durability, and platform compatibility. Evaluating these key differences side-by-side ensures you select gear that perfectly matches your playstyle.",
    faqText: "The best {keyword} depends on your primary focus—whether you want ultra-low latency for competitive play or maximum ergonomic comfort for long sessions. Check the comparison table to find your ideal match."
  },
  tools: {
    intro: "Compare the top-rated options for {keyword} side by side. See exactly how these leading tools stack up against one another on critical factors such as power output, durability, battery ecosystem, and overall precision.",
    keyDiff: "Tools can vary significantly in their motor efficiency, material construction, and safety features. Evaluating these key differences ensures you select equipment that can handle the specific demands of your projects.",
    faqText: "The ideal {keyword} depends on whether you need light-duty versatility for home projects or rugged, industrial-grade reliability for job sites. Review the comparison to find the tool that fits your specific needs."
  },
  default: {
    intro: "Compare the top-rated options for {keyword} side by side using our detailed evaluation matrix. See exactly how these leading solutions stack up against one another on critical factors such as price, overall quality, user popularity, and long-term value.",
    keyDiff: "Each option has distinct unique strengths and potential drawbacks depending on your specific priorities. Evaluating these key differences side-by-side ensures you select the most optimal fit for your individual or business requirements.",
    faqText: "The ideal choice ultimately depends on your primary priorities—whether you prioritize budget-friendly pricing, premium build quality, or specific advanced features. Carefully review the comparative data in the table above to find the perfect match that aligns with your criteria."
  }
};

function generateComparison(kw) {
  const { month, year } = getMonthYear();

  const readableText = (kw.slug || '').replace(/-/g, ' ');
  const pageTypeWord = kw.page_type || 'comparison';
  const typeRegex = new RegExp('\\s+' + pageTypeWord + '$', 'i');

  const hasSuffix = typeRegex.test(readableText);
  const topic = (hasSuffix ? readableText.replace(typeRegex, '') : readableText) || kw.primary_keyword;
  const topicTitle = titleCase(topic);
  const h1Text = hasSuffix ? titleCase(readableText) : `${topicTitle} — Side-by-Side Comparison`;

  const secondaries = JSON.parse(kw.secondary_keywords || '[]');
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const apexName = APEX_NAMES[apexSlug] || 'Guide';

  const category = SITE_TO_CATEGORY[kw.target_site] || 'default';
  const content = COMPARISON_CONTENT[category] || COMPARISON_CONTENT['default'];
  const introText = content.intro.replace(/\{keyword\}/g, topic);
  const keyDiffText = content.keyDiff.replace(/\{keyword\}/g, topic);
  const faqText = content.faqText.replace(/\{keyword\}/g, topic);

  return `${SEED_CSS}
<div class="seed-page">
  <h1>${esc(h1Text)}</h1>
  <p class="seed-meta">Updated ${month} ${year} · ${(kw.total_volume || 0).toLocaleString()}+ monthly searches</p>

  <div class="seed-section">
    <h2>${esc(topicTitle)} Comparison</h2>
    <p>${esc(introText)}</p>
    <table class="seed-compare-table">
      <thead>
        <tr><th>Feature</th><th>Option A</th><th>Option B</th><th>Option C</th></tr>
      </thead>
      <tbody>
        <tr><td>Price</td><td>$$</td><td>$$$</td><td>$</td></tr>
        <tr><td>Quality</td><td>High</td><td>Premium</td><td>Good</td></tr>
        <tr><td>Popularity</td><td>★★★★</td><td>★★★★★</td><td>★★★</td></tr>
        <tr><td>Value</td><td>Great</td><td>Good</td><td>Best</td></tr>
      </tbody>
    </table>
  </div>

  <div class="seed-section">
    <h2>Key Differences</h2>
    <ul>
      <li>Search volume: ${(kw.total_volume || 0).toLocaleString()} searches per month</li>
      ${secondaries.length ? `<li>Related comparisons: ${secondaries.map(s => esc(s)).join(', ')}</li>` : ''}
      <li>${esc(keyDiffText)}</li>
    </ul>
  </div>

  <div class="seed-section">
    <h2>Frequently Asked Questions</h2>
    <div class="faq-item">
      <h3>Which ${esc(topic)} is best?</h3>
      <p>${esc(faqText)}</p>
    </div>
  </div>

  <p class="seed-explore">Explore more: <a href="https://gab.ae/${apexSlug}">${esc(apexName)}</a></p>
</div>`;
}

const GENERATORS = {
  educational: generateEducational,
  listicle: generateListicle,
  calculator: generateCalculator,
  comparison: generateComparison,
};

/**
 * Main seed function — processes 1 queued keyword per call.
 * @param {Object} env - Worker env with DB binding
 * @returns {Object} Result summary
 */
export async function seedPages(env) {
  // 1. Get next queued keyword
  const kw = await env.DB.prepare(
    "SELECT * FROM keyword_queue WHERE status = 'queued' ORDER BY score DESC LIMIT 1"
  ).first();

  if (!kw) {
    return { seeded: false, reason: 'no queued keywords' };
  }

  // 2. Check if slug already exists in pages
  const existing = await env.DB.prepare(
    "SELECT slug FROM pages WHERE slug = ?"
  ).bind(kw.slug).first();

  if (existing) {
    // Mark as skipped in keyword_queue
    await env.DB.prepare(
      "UPDATE keyword_queue SET status = 'skipped' WHERE slug = ?"
    ).bind(kw.slug).run();
    return { seeded: false, reason: 'slug already exists', slug: kw.slug };
  }

  // 3. Generate template HTML
  const pageType = kw.page_type || 'educational';
  const generator = GENERATORS[pageType] || GENERATORS.educational;
  const html = generator(kw);

  // 4. Build page metadata
  const pkTitle = titleCase(kw.primary_keyword);
  const hasPrefix = /^(best|top|how to|what is)\s/i.test(kw.primary_keyword);
  const listicleTitle = hasPrefix ? `${pkTitle} (${new Date().getFullYear()})` : `Top 10 ${pkTitle} (${new Date().getFullYear()})`;

  const titleSuffix = {
    educational: `${pkTitle} — Complete Guide`,
    listicle: listicleTitle,
    calculator: `${pkTitle} Calculator`,
    comparison: `${pkTitle} — Comparison`,
  };
  const title = (titleSuffix[pageType] || pkTitle) + ' | gab.ae';
  const description = `Everything you need to know about ${kw.primary_keyword}. ${(kw.total_volume || 0).toLocaleString()}+ monthly searches.`;
  const category = SITE_TO_CATEGORY[kw.target_site] || 'tools';
  const apexSlug = SITE_TO_APEX[kw.target_site] || 'software-ai-infrastructure-guide-2026';
  const now = new Date().toISOString().replace('T', ' ').slice(0, 19);

  // 5. Insert into pages table (engine column has NOT NULL constraint)
  await env.DB.prepare(
    `INSERT INTO pages (slug, title, description, category, engine, html, status, quality, keyword, keyword_volume, keyword_kd, page_type, target_site, published_at, updated_at, created_at)
     VALUES (?, ?, ?, ?, 'seed', ?, 'live', 'template', ?, ?, ?, ?, ?, ?, ?, ?)`
  ).bind(
    kw.slug, title, description, category, html,
    kw.primary_keyword, kw.total_volume || 0, kw.avg_kd || 0, pageType, kw.target_site || '',
    now, now, now
  ).run();

  // 6. Insert into tracked_pages
  try {
    await env.DB.prepare(
      `INSERT OR IGNORE INTO tracked_pages (domain, path, title, apex_slug, cluster, status)
       VALUES ('gab.ae', ?, ?, ?, ?, 'active')`
    ).bind('/' + kw.slug, title, apexSlug, pageType).run();
  } catch (e) {
    console.log(`⚠️ tracked_pages insert failed: ${e.message}`);
  }

  // 7. Update keyword_queue status
  await env.DB.prepare(
    "UPDATE keyword_queue SET status = 'published', published_at = ? WHERE slug = ?"
  ).bind(now, kw.slug).run();

  console.log(`🌱 Seeded template page: ${kw.slug} (${pageType}, vol=${kw.total_volume})`);

  return {
    seeded: true,
    slug: kw.slug,
    keyword: kw.primary_keyword,
    pageType,
    volume: kw.total_volume,
    apexSlug,
  };
}
