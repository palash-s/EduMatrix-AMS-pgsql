import { API_BASE_URL } from '../constants/brand';
import { httpJson } from './http';

export async function login({ username, password, deviceId }) {
  return httpJson(`${API_BASE_URL}/api/v1/auth/login`, {
    method: 'POST',
    body: { username, password, device_id: deviceId },
  });
}

export async function getAttendance({ token }) {
  return httpJson(`${API_BASE_URL}/api/v1/student/attendance/subjects`, { token });
}

export async function getTimetable({ token }) {
  return httpJson(`${API_BASE_URL}/api/v1/student/timetable`, { token });
}

export async function getLeaves({ token }) {
  return httpJson(`${API_BASE_URL}/api/v1/student/leaves`, { token });
}

export async function getResults({ token }) {
  return httpJson(`${API_BASE_URL}/api/v1/student/results`, { token });
}

export async function getNotifications({ token }) {
  return httpJson(`${API_BASE_URL}/api/v1/notifications`, { token });
}

export async function getStudentDashboard({ userId }) {
  return httpJson(`${API_BASE_URL}/api/student/dashboard?user_id=${encodeURIComponent(String(userId))}`);
}

export async function getCurrentTerm() {
  return httpJson(`${API_BASE_URL}/api/current_term`);
}

export async function getPendingFeedback({ userId }) {
  return httpJson(`${API_BASE_URL}/api/feedback/pending_list?user_id=${encodeURIComponent(String(userId))}`);
}

export async function submitDetentionTask({ detentionId, submissionUrl }) {
  return httpJson(`${API_BASE_URL}/api/detention/submit_task`, {
    method: 'POST',
    body: {
      detention_id: detentionId,
      submission_url: submissionUrl,
    },
  });
}
