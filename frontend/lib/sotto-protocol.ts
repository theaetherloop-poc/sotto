/**
 * Static mock protocol for the "Generate protocol" screen (Screen 2 of the mockup).
 *
 * Transcribed verbatim from Sotto_UI_Mockup.html. In production this would come from the Aether
 * Loop recommendation engine; for the demo it is fixed data for the Maya Chen consult.
 */

export type FocusArea = {
  rank: number;
  name: string;
  why: string;
};

export type Supplement = {
  name: string;
  /** Priority = supports a top-3 focus area. Default-checked rows aside, this drives the badge. */
  priority: boolean;
  dosage: string;
  frequency: string;
  focusArea: string;
  why: string;
  /** Whether the Add checkbox starts checked (it's a suggestion the doctor curates). */
  defaultChecked: boolean;
};

/** Top-3 focus areas, expanded with a one-line "why". */
export const PRIORITIZED_FOCUS_AREAS: FocusArea[] = [
  {
    rank: 1,
    name: 'Mitochondrial & Energy',
    why: 'Fatigue with ferritin falling 52→18 and HRV down — restore iron and energy.',
  },
  {
    rank: 2,
    name: 'Hormonal Health',
    why: 'Heavier menses likely driving iron loss; TSH high-normal at 3.8.',
  },
  {
    rank: 3,
    name: 'Stress-Axis & Nervous System',
    why: 'Stress 8/10, anxiety, waking at night, HRV ~21% below baseline.',
  },
];

/** Remaining focus areas, listed only (rank + name). */
export const OTHER_FOCUS_AREAS: { rank: number; name: string }[] = [
  { rank: 4, name: 'Gut Health' },
  { rank: 5, name: 'Immune & Inflammation' },
  { rank: 6, name: 'Detox' },
  { rank: 7, name: 'Skin' },
];

export const SUPPLEMENTS: Supplement[] = [
  {
    name: 'Iron bisglycinate',
    priority: true,
    dosage: '25–50 mg',
    frequency: 'Every other day, with vit C',
    focusArea: 'Mitochondrial & Energy · Hormonal',
    why: 'Ferritin 18, iron sat 11%; recheck 8–12 wk; address menses.',
    defaultChecked: true,
  },
  {
    name: 'Vitamin D3 / K2',
    priority: false,
    dosage: '5,000 IU',
    frequency: 'Once daily, fatty meal',
    focusArea: 'Immune & Inflammation · Cardiometabolic',
    why: 'Level 22; goal 50–90; recheck in 6 months.',
    defaultChecked: true,
  },
  {
    name: 'Omega-3',
    priority: false,
    dosage: '1.5–3 g',
    frequency: 'Once daily, fatty meal',
    focusArea: 'Immune & Inflammation · Skin',
    why: 'hs-CRP elevated + skin issues.',
    defaultChecked: true,
  },
  {
    name: 'Magnesium glycinate',
    priority: true,
    dosage: '300–400 mg',
    frequency: 'Evening',
    focusArea: 'Stress-Axis',
    why: 'Stress, anxiety, night waking; supports sleep.',
    defaultChecked: true,
  },
  {
    name: 'Ashwagandha (KSM-66)',
    priority: true,
    dosage: '300–600 mg',
    frequency: 'Once–twice daily',
    focusArea: 'Stress-Axis',
    why: 'Cortisol regulation. Avoid in pregnancy.',
    defaultChecked: true,
  },
  {
    name: 'Spore probiotic',
    priority: false,
    dosage: '1–2 caps',
    frequency: 'Daily, titrate up',
    focusArea: 'Gut Health',
    why: 'Bloating; aids iron absorption.',
    defaultChecked: false,
  },
];
