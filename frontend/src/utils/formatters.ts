import { EligibilityStatus } from '../types';

export * from './fieldMapping';

export function getEligibilityBadgeColor(status: EligibilityStatus): string {
  switch (status) {
    case 'Eligible':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'Not Eligible':
      return 'bg-rose-50 text-rose-700 border-rose-200';
    case 'More Information Required':
      return 'bg-amber-50 text-amber-700 border-amber-200';
    default:
      return 'bg-slate-50 text-slate-700 border-slate-200';
  }
}

export function formatDate(isoDateString?: string): string {
  if (!isoDateString) return 'N/A';
  try {
    return new Date(isoDateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return isoDateString;
  }
}
