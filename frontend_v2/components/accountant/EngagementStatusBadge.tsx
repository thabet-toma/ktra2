import React from 'react';
import type { EngagementStatus } from '../../types/accountant';
import { ENGAGEMENT_STATUS_LABELS, ENGAGEMENT_STATUS_TONES } from '../../utils/engagement';

export const EngagementStatusBadge: React.FC<{ status: EngagementStatus }> = ({ status }) => (
  <span className={`inline-flex rounded-full px-3 py-1 text-xs font-black ${ENGAGEMENT_STATUS_TONES[status]}`}>
    {ENGAGEMENT_STATUS_LABELS[status]}
  </span>
);

