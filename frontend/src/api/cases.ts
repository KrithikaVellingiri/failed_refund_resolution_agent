import { fetchApi } from './client';
import { queueFixture, caseDetailFixture } from './fixtures';
import { CaseListItem, CaseDetail } from './types';

// The assignment says:
// - Existing implemented endpoint + successful response -> real API data.
// - Endpoint not implemented yet -> explicitly use the development fixture adapter.
// - Real API returns an error -> show the specified error state; do not silently substitute fixtures.

export async function getCases(): Promise<CaseListItem[]> {
  try {
    return await fetchApi<CaseListItem[]>('/cases');
  } catch (error: any) {
    if (error.status === 404 && error.detail === 'Not Found') {
      console.warn('API Endpoint /cases not found. Using development fixture.');
      return queueFixture;
    }
    throw error;
  }
}

export async function getCaseDetail(caseId: string): Promise<CaseDetail> {
  try {
    return await fetchApi<CaseDetail>(`/cases/${caseId}`);
  } catch (error: any) {
    if (error.status === 404 && error.detail === 'Not Found') {
      console.warn(`API Endpoint /cases/${caseId} not found. Using development fixture.`);
      return { ...caseDetailFixture, case_id: caseId };
    }
    throw error;
  }
}
