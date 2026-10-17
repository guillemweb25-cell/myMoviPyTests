import type { Word } from "./types.ts";

export type Phrase = {
  words: Word[];
  start: number;
  end: number;
};

/**
 * Agrupa palabras en frases cortas, con los mismos criterios que
 * `SubtitleEngine._group_words_into_phrases` del backend (tope de palabras,
 * pausa larga o puntuación), para que el camino FX y el camino ASS partan las
 * frases igual y el clip se lea parecido con worker y sin worker.
 */
export const groupWords = (
  words: Word[],
  maxWords: number,
  maxGap = 0.4,
): Phrase[] => {
  const phrases: Phrase[] = [];
  let current: Word[] = [];

  words.forEach((word, i) => {
    current.push(word);
    const isLast = i === words.length - 1;
    const longPause = !isLast && words[i + 1]!.start - word.end > maxGap;
    const punctuation = /[.,!?:;]$/.test(word.text.trim());

    if (current.length >= maxWords || isLast || longPause || punctuation) {
      phrases.push({
        words: current,
        start: current[0]!.start,
        end: current[current.length - 1]!.end,
      });
      current = [];
    }
  });

  return phrases;
};

/**
 * La frase visible en un instante. Entre frases se mantiene la anterior hasta
 * que empieza la siguiente, para que el subtítulo no parpadee en las pausas.
 */
export const phraseAt = (phrases: Phrase[], t: number): Phrase | null => {
  let visible: Phrase | null = null;
  for (const phrase of phrases) {
    if (phrase.start <= t) visible = phrase;
    else break;
  }
  return visible;
};
