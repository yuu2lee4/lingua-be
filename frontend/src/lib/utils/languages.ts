export interface Language {
  code: string;
  nameZh: string;
  nameEn: string;
}

export const LANGUAGES: Record<string, Language> = {
  "ar": { code: "ar", nameZh: "阿拉伯语", nameEn: "Arabic" },
  "de-DE": { code: "de-DE", nameZh: "德语", nameEn: "German" },
  "en-US": { code: "en-US", nameZh: "英语", nameEn: "English" },
  "es-ES": { code: "es-ES", nameZh: "西班牙语", nameEn: "Spanish" },
  "fr-FR": { code: "fr-FR", nameZh: "法语", nameEn: "French" },
  "id-ID": { code: "id-ID", nameZh: "印尼语", nameEn: "Indonesian" },
  "ja-JP": { code: "ja-JP", nameZh: "日语", nameEn: "Japanese" },
  "ko-KR": { code: "ko-KR", nameZh: "韩语", nameEn: "Korean" },
  "pt-BR": { code: "pt-BR", nameZh: "葡萄牙语", nameEn: "Portuguese" },
  "ru-RU": { code: "ru-RU", nameZh: "俄语", nameEn: "Russian" },
  "uk-UA": { code: "uk-UA", nameZh: "乌克兰语", nameEn: "Ukrainian" },
  "vi-VN": { code: "vi-VN", nameZh: "越南语", nameEn: "Vietnamese" },
  "zh-CN": { code: "zh-CN", nameZh: "简体中文", nameEn: "Chinese (Simplified)" },
  "zh-TW": { code: "zh-TW", nameZh: "繁体中文", nameEn: "Chinese (Traditional)" },
} as const;

export const LANGUAGE_CODES = Object.keys(LANGUAGES);

export const TARGET_LANGUAGES = LANGUAGE_CODES.filter((code) => code !== "en-US");

export function getLanguageName(code: string, locale: "zh" | "en" = "en"): string {
  const lang = LANGUAGES[code];
  if (!lang) return code;
  return locale === "zh" ? lang.nameZh : lang.nameEn;
}
