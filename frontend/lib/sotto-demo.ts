/**
 * Static demo session context for the Sotto consult dashboard.
 *
 * Mirrors demo_data/sotto_demo_patient.json (Maya Chen). Per the build spec, the patient label
 * and loaded-context chips are populated from session context at start and are static for the
 * demo — the live platform integration is mocked.
 */

export type LoadedContextChip = {
  /** Tabler icon name (without the `ti ti-` prefix). */
  icon: string;
  label: string;
};

export const DEMO_PATIENT = {
  /** First name, used for transcript speaker labels (e.g. "Maya"). */
  firstName: 'Maya',
  fullName: 'Maya Chen',
  age: 41,
  /** Single-letter biological sex shown in the patient label. */
  sex: 'F',
  context: 'consult',
} as const;

/** Label shown in the top bar, e.g. "Maya Chen · 41 F · consult". */
export const DEMO_PATIENT_LABEL = `${DEMO_PATIENT.fullName} · ${DEMO_PATIENT.age} ${DEMO_PATIENT.sex} · ${DEMO_PATIENT.context}`;

export const LOADED_CONTEXT_CHIPS: LoadedContextChip[] = [
  { icon: 'user', label: 'Patient info' },
  { icon: 'flask', label: 'Latest blood panel · May 20' },
  { icon: 'history', label: 'Lab history · 14 months' },
  { icon: 'device-watch', label: 'Oura · connected' },
];
