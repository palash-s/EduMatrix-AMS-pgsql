import React, { useEffect, useMemo, useState } from 'react';
import { Linking, Modal, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useIsFocused } from '@react-navigation/native';

import Svg, { Circle } from 'react-native-svg';

import { getCurrentTerm, getPendingFeedback, getStudentDashboard, submitDetentionTask } from '../api/ams';
import { API_BASE_URL } from '../constants/brand';
import { useSession } from '../state/session';

export default function DashboardScreen({ navigation }) {
  const { user, logout } = useSession();
  const isFocused = useIsFocused();

  const userId = user?.user_id;

  const [status, setStatus] = useState('loading');
  const [error, setError] = useState('');
  const [term, setTerm] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [data, setData] = useState(null);

  const [resultsOpen, setResultsOpen] = useState(false);
  const [detentionOpen, setDetentionOpen] = useState(false);
  const [submissionUrl, setSubmissionUrl] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const pct = Number(data?.stats?.percentage || 0);
  const isDefaulter = Boolean(data?.stats?.is_defaulter);

  const termLabel = useMemo(() => {
    if (!term) return '—';
    if (term.academic_year && term.semester) return `${term.academic_year} • ${term.semester}`;
    return term.current_term || '—';
  }, [term]);

  async function load() {
    if (!userId) return;
    setError('');
    setStatus('loading');
    try {
      const [t, d, f] = await Promise.all([
        getCurrentTerm(),
        getStudentDashboard({ userId }),
        getPendingFeedback({ userId }),
      ]);
      setTerm(t);
      setData(d);
      setFeedback(f);
      setStatus('ready');
    } catch (e) {
      setError(e?.message || 'Failed to load');
      setStatus('ready');
    }
  }

  useEffect(() => {
    if (!isFocused) return;
    load();
    // Auto-refresh is disabled globally.
    return undefined;
  }, [isFocused, userId]);

  async function onSubmitDetention() {
    const det = data?.detention;
    if (!det?.id) return;
    const url = (submissionUrl || '').trim();
    if (!url) return;

    setSubmitting(true);
    try {
      await submitDetentionTask({ detentionId: det.id, submissionUrl: url });
      setDetentionOpen(false);
      setSubmissionUrl('');
      await load();
    } catch (e) {
      setError(e?.message || 'Failed to submit');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ScrollView className="flex-1 bg-mit-slateBg">
      {/* Top header */}
      <View className="bg-white border-b border-slate-200 px-5 pt-14 pb-4">
        <View className="flex-row items-end justify-between">
          <View className="flex-1 pr-4">
            <Text className="text-slate-900 text-2xl font-extrabold">
              Hello, <Text className="text-mit-purple">{data?.profile?.name || 'Student'}</Text>
            </Text>
            <Text className="text-slate-500 text-xs mt-1">
              {data?.profile?.class ? `${data.profile.class} | ` : ''}Roll No: {data?.profile?.roll || '—'}
            </Text>
          </View>

          <View className="items-end">
            <Text className="text-[10px] font-extrabold text-slate-400 uppercase">Academic Term</Text>
            <Text className="text-xs font-extrabold text-slate-700 mt-1">{termLabel}</Text>
          </View>
        </View>

        <View className="flex-row gap-3 mt-4">
          <TouchableOpacity onPress={load} className="px-4 py-2 rounded-xl bg-slate-100">
            <Text className="text-slate-700 font-extrabold text-xs">Refresh</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={logout} className="px-4 py-2 rounded-xl bg-slate-100">
            <Text className="text-red-700 font-extrabold text-xs">Logout</Text>
          </TouchableOpacity>
        </View>
      </View>

      <View className="px-5 py-6">
        {error ? (
          <View className="bg-red-50 border border-red-200 rounded-xl p-4 mb-4">
            <Text className="text-red-700 font-bold">{error}</Text>
          </View>
        ) : null}

        {/* Feedback alert (matches web logic) */}
        {feedback?.active && Array.isArray(feedback?.subjects) && feedback.subjects.length > 0 ? (
          <View className="bg-purple-50 border-l-4 border-mit-purple p-4 rounded-r-xl border border-purple-100 mb-4 flex-row items-center justify-between">
            <View className="flex-1 pr-3">
              <Text className="text-mit-purple font-extrabold text-sm">Feedback Required</Text>
              <Text className="text-purple-700 text-xs mt-1">
                {feedback.cycle_name || 'Active cycle'}: {feedback.subjects.length} subjects pending.
              </Text>
            </View>
            <TouchableOpacity
              onPress={() => Linking.openURL(`${API_BASE_URL}/student/feedback`)}
              className="px-4 py-2 rounded-lg bg-mit-purple"
            >
              <Text className="text-white font-extrabold text-xs">Give Feedback</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {/* Detention alert */}
        {data?.detention ? (
          <View
            className={`p-4 rounded-xl border shadow-sm mb-4 flex-row items-center justify-between ${
              data.detention.status === 'In_Review'
                ? 'bg-yellow-50 border-yellow-200'
                : 'bg-red-50 border-red-200'
            }`}
          >
            <View className="flex-1 pr-3">
              <Text
                className={`font-extrabold text-sm ${
                  data.detention.status === 'In_Review' ? 'text-yellow-800' : 'text-red-800'
                }`}
              >
                {data.detention.status === 'In_Review' ? 'STATUS: UNDER REVIEW' : 'ACTION REQUIRED: Active Detention'}
              </Text>
              <Text
                className={`text-xs mt-1 ${
                  data.detention.status === 'In_Review' ? 'text-yellow-700' : 'text-red-700'
                }`}
              >
                {data.detention.status === 'In_Review'
                  ? 'Faculty is reviewing your submission.'
                  : `Pending: ${data.detention.reason}`}
              </Text>
            </View>
            <TouchableOpacity
              onPress={() => {
                setSubmissionUrl(data.detention.submission_url || '');
                setDetentionOpen(true);
              }}
              className={`px-3 py-2 rounded-lg ${
                data.detention.status === 'In_Review' ? 'bg-yellow-600' : 'bg-red-700'
              }`}
            >
              <Text className="text-white font-extrabold text-xs">
                {data.detention.status === 'In_Review' ? 'View Status' : 'Submit Task'}
              </Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {/* Term grant alert */}
        {data?.term_grant ? (
          <View
            className={`rounded-xl p-5 mb-4 border ${
              data.term_grant.status === 'Granted'
                ? 'bg-green-600 border-green-700'
                : data.term_grant.status === 'Provisional'
                  ? 'bg-yellow-50 border-yellow-200'
                  : 'bg-red-50 border-red-200'
            }`}
          >
            {data.term_grant.status === 'Granted' ? (
              <>
                <Text className="text-white text-lg font-extrabold">Term Grant Ticket Issued</Text>
                <Text className="text-green-100 text-xs mt-1">You are eligible for the End Semester Examination.</Text>
              </>
            ) : data.term_grant.status === 'Provisional' ? (
              <>
                <Text className="text-yellow-800 text-lg font-extrabold">Provisional Eligibility</Text>
                <Text className="text-yellow-700 text-xs mt-1">Please contact your Class Teacher immediately.</Text>
                {data.term_grant.remarks ? (
                  <Text className="text-yellow-700 text-[11px] mt-3">Reason: {data.term_grant.remarks}</Text>
                ) : null}
              </>
            ) : (
              <>
                <Text className="text-red-800 text-lg font-extrabold">Not Eligible (Detained)</Text>
                <Text className="text-red-700 text-xs mt-1">You have been detained due to non-compliance with university norms.</Text>
                {data.term_grant.remarks ? (
                  <Text className="text-red-700 text-[11px] mt-3">Reason: {data.term_grant.remarks}</Text>
                ) : null}
              </>
            )}
          </View>
        ) : null}

        {/* Overall Attendance card */}
        <View className="bg-white rounded-xl shadow-sm border border-purple-100 p-5 relative overflow-hidden flex-row items-center justify-between mb-4">
          <View className="absolute top-0 left-0 w-1 h-full bg-mit-purple" />
          <View className="flex-1 pr-4">
            <View className="flex-row items-center gap-3">
              <Text className="text-slate-500 font-extrabold text-[10px] uppercase tracking-wider">Overall Attendance</Text>
              <View
                className={`px-2 py-0.5 rounded-full ${
                  isDefaulter ? 'bg-red-100' : 'bg-green-100'
                }`}
              >
                <Text className={`text-[10px] font-extrabold ${isDefaulter ? 'text-red-700' : 'text-green-700'}`}>
                  {status === 'loading' ? 'Checking…' : isDefaulter ? 'Risk: Defaulter' : 'Good Standing'}
                </Text>
              </View>
            </View>

            <View className="flex-row items-baseline gap-2 mt-2">
              <Text className="text-4xl font-black text-mit-purple">{data?.stats?.attended ?? '—'}</Text>
              <Text className="text-sm text-slate-400">
                / <Text className="text-slate-500">{data?.stats?.total_lectures ?? '—'}</Text> Sessions
              </Text>
            </View>
            <Text className="text-xs text-slate-400 mt-2">Maintain 75% to appear for exams.</Text>
          </View>

          <AttendanceRing
            percentage={Number.isFinite(pct) ? pct : 0}
            strokeColor={isDefaulter ? '#ef4444' : '#00a887'}
          />
        </View>

        {/* Subject Performance */}
        <View className="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden mb-4">
          <View className="p-4 border-b border-slate-50 bg-slate-50/30 flex-row items-center justify-between">
            <Text className="font-extrabold text-slate-800">Subject Performance</Text>
          </View>
          <View className="p-4">
            {status === 'loading' ? (
              <View className="gap-3">
                <View className="h-20 w-full bg-slate-100 rounded-lg" />
                <View className="h-20 w-full bg-slate-100 rounded-lg" />
              </View>
            ) : !data?.subject_wise || data.subject_wise.length === 0 ? (
              <Text className="text-center text-slate-400 py-4 text-sm">No data available.</Text>
            ) : (
              <View className="gap-3">
                {data.subject_wise.map((sub) => {
                  const sp = Number(sub?.percentage || 0);
                  const ok = sp >= 75;
                  const barClass = ok ? 'bg-mit-teal' : 'bg-red-500';
                  const txtClass = ok ? 'text-green-700' : 'text-red-700';
                  return (
                    <View
                      key={`${sub.code || sub.subject}`}
                      className="p-3 border border-slate-100 rounded-lg"
                    >
                      <View className="flex-row items-center justify-between mb-2">
                        <Text className="font-extrabold text-slate-700 text-xs flex-1 pr-2" numberOfLines={1}>
                          {sub.subject}
                        </Text>
                        <Text className={`text-xs font-extrabold ${txtClass}`}>{sp}%</Text>
                      </View>
                      <View className="w-full bg-slate-100 rounded-full h-1.5 overflow-hidden">
                        <View className={`${barClass} h-1.5 rounded-full`} style={{ width: `${Math.max(0, Math.min(100, sp))}%` }} />
                      </View>
                      <View className="flex-row items-center justify-between mt-2">
                        <Text className="text-[10px] text-slate-400">{sub.teacher || 'Unassigned'}</Text>
                        <Text className="text-[10px] text-slate-400">
                          {sub.attended}/{sub.conducted} Attended
                        </Text>
                      </View>
                    </View>
                  );
                })}
              </View>
            )}
          </View>
        </View>

        {/* Quick Actions */}
        <View className="bg-white rounded-xl shadow-sm border border-slate-100 p-4 mb-4">
          <Text className="text-[10px] font-extrabold text-slate-400 uppercase mb-3">Quick Actions</Text>
          <View className="flex-row gap-3">
            <TouchableOpacity
              onPress={() => navigation.navigate('Leaves')}
              className="flex-1 items-center justify-center p-3 rounded-lg border border-purple-100 bg-purple-50"
            >
              <Text className="text-mit-purple font-extrabold text-xs">Apply Leave</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => navigation.navigate('Timetable')}
              className="flex-1 items-center justify-center p-3 rounded-lg border border-teal-100 bg-teal-50"
            >
              <Text className="text-mit-teal font-extrabold text-xs">Timetable</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity
            onPress={() => setResultsOpen(true)}
            className="mt-3 items-center justify-center p-3 rounded-lg border border-blue-100 bg-blue-50"
          >
            <Text className="text-blue-700 font-extrabold text-xs">View Exam Results</Text>
          </TouchableOpacity>
        </View>

        {/* Mentor + meeting */}
        {data?.mentor ? (
          <>
            <View className="bg-white rounded-xl shadow-sm border border-teal-100 p-4 mb-4 relative overflow-hidden">
              <View className="absolute top-0 left-0 w-1 h-full bg-mit-teal" />
              <Text className="text-[10px] font-extrabold text-slate-400 uppercase mb-3">My Mentor</Text>
              <View className="flex-row items-center gap-3">
                <View className="w-10 h-10 rounded-full bg-teal-50 items-center justify-center">
                  <Text className="font-extrabold text-mit-teal text-sm">
                    {String(data.mentor.name || 'M').slice(0, 1)}
                  </Text>
                </View>
                <View className="flex-1">
                  <Text className="text-sm font-extrabold text-slate-800">{data.mentor.name}</Text>
                  {data.mentor.email ? (
                    <Text className="text-xs text-blue-700 mt-0.5" onPress={() => Linking.openURL(`mailto:${data.mentor.email}`)}>
                      {data.mentor.email}
                    </Text>
                  ) : null}
                </View>
              </View>
              <Text className="text-[10px] text-slate-400 mt-2 text-right">Group: {data.mentor.batch_name}</Text>
            </View>

            {data?.meeting ? (
              <View className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4">
                <Text className="text-blue-900 font-extrabold text-sm">Upcoming Mentor Meeting</Text>
                <Text className="text-blue-700 text-xs mt-1 font-semibold">{data.meeting.agenda}</Text>
                <View className="flex-row gap-3 mt-3">
                  <View className="bg-white px-2 py-1 rounded border border-blue-100">
                    <Text className="text-blue-700 text-xs font-mono">{data.meeting.date}</Text>
                  </View>
                  <View className="bg-white px-2 py-1 rounded border border-blue-100">
                    <Text className="text-blue-700 text-xs font-mono">{data.meeting.time}</Text>
                  </View>
                </View>
              </View>
            ) : null}
          </>
        ) : null}

        {/* Event History */}
        <View className="bg-white rounded-xl shadow-sm border border-slate-100 p-4 mb-4">
          <Text className="text-[10px] font-extrabold text-slate-400 uppercase mb-4">Event History</Text>
          {status === 'loading' ? (
            <View className="h-10 w-full bg-slate-100 rounded-lg" />
          ) : !data?.events || data.events.length === 0 ? (
            <Text className="text-center text-slate-400 py-2 text-xs">No events participated yet.</Text>
          ) : (
            <View className="gap-2">
              {data.events.map((evt) => (
                <View key={`${evt.name}-${evt.date}-${evt.role}`} className="flex-row items-start justify-between py-2 border-b border-slate-50">
                  <View className="flex-1 pr-3">
                    <Text className="font-extrabold text-slate-800 text-xs">{evt.name}</Text>
                    <Text className="text-[10px] text-slate-500 mt-1">{evt.date}</Text>
                  </View>
                  <View className="bg-purple-50 px-2 py-1 rounded">
                    <Text className="text-[10px] font-extrabold text-mit-purple">{evt.role}</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>

        {/* Recent Activity */}
        <View className="bg-white rounded-xl shadow-sm border border-slate-100 p-4 mb-8">
          <Text className="text-[10px] font-extrabold text-slate-400 uppercase mb-4">Recent Activity</Text>
          {status === 'loading' ? null : !data?.recent_activity || data.recent_activity.length === 0 ? (
            <Text className="text-center text-slate-400 py-4 text-sm">No recent activity.</Text>
          ) : (
            <View className="border-l border-slate-200 ml-2">
              {data.recent_activity.map((item, idx) => {
                const present = item.status === 'Present' || item.status === 'OnDuty';
                const dotClass = present ? 'bg-green-500' : 'bg-red-500';
                return (
                  <View key={`${item.subject}-${item.date}-${idx}`} className="pl-4 pb-6 relative">
                    <View className={`absolute -left-1 top-2 w-2.5 h-2.5 rounded-full ${dotClass} border-2 border-white`} />
                    <View className="flex-row items-start justify-between">
                      <View className="flex-1 pr-3">
                        <Text className="font-extrabold text-slate-800 text-sm">{item.subject}</Text>
                        <Text className="text-[10px] text-slate-400 mt-1">
                          {item.date} • {item.time}
                        </Text>
                      </View>
                      <View className={`px-2 py-1 rounded ${present ? 'bg-green-50' : 'bg-red-50'}`}>
                        <Text className={`text-[10px] font-extrabold ${present ? 'text-green-700' : 'text-red-700'}`}>
                          {item.status}
                        </Text>
                      </View>
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </View>
      </View>

      {/* Results modal */}
      <Modal visible={resultsOpen} transparent animationType="fade" onRequestClose={() => setResultsOpen(false)}>
        <View className="flex-1 bg-black/50 items-center justify-center px-4">
          <View className="bg-white w-full max-w-4xl rounded-2xl overflow-hidden">
            <View className="p-4 border-b border-slate-200 bg-slate-50 flex-row items-center justify-between">
              <View>
                <Text className="text-lg font-extrabold text-mit-purple">Progress Card</Text>
                <Text className="text-[11px] text-slate-500">Internal Assessment Scores</Text>
              </View>
              <TouchableOpacity onPress={() => setResultsOpen(false)} className="px-3 py-2 rounded-lg bg-slate-100">
                <Text className="text-slate-700 font-extrabold text-xs">Close</Text>
              </TouchableOpacity>
            </View>

            <ScrollView style={{ maxHeight: 520 }}>
              {!data?.results || data.results.length === 0 ? (
                <Text className="p-6 text-center text-slate-400">No results published yet.</Text>
              ) : (
                <View className="p-4 gap-3">
                  {data.results.map((r) => (
                    <View key={`${r.code}-${r.subject}`} className="border border-slate-200 rounded-xl p-4">
                      <Text className="font-extrabold text-slate-900">
                        {r.subject} <Text className="text-slate-400 text-xs">({r.code})</Text>
                      </Text>
                      <View className="flex-row justify-between mt-3">
                        <ScoreChip label="TA1" value={r.ta1} />
                        <ScoreChip label="TA2" value={r.ta2} />
                        <ScoreChip label="TA3" value={r.ta3} />
                      </View>
                      <Text className="text-[11px] text-slate-500 mt-3">
                        {r.a1 !== '-' && r.a1 !== undefined ? `A1:${r.a1} ` : ''}
                        {r.a2 !== '-' && r.a2 !== undefined ? `A2:${r.a2}` : ''}
                      </Text>
                    </View>
                  ))}
                </View>
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Detention modal */}
      <Modal visible={detentionOpen} transparent animationType="fade" onRequestClose={() => setDetentionOpen(false)}>
        <View className="flex-1 bg-black/50 items-center justify-center px-4">
          <View className="bg-white w-full max-w-md rounded-2xl overflow-hidden">
            <View className="p-4 border-b border-slate-200 flex-row items-center justify-between">
              <Text className="text-lg font-extrabold text-mit-purple">Detention Task</Text>
              <TouchableOpacity onPress={() => setDetentionOpen(false)} className="px-3 py-2 rounded-lg bg-slate-100">
                <Text className="text-slate-700 font-extrabold text-xs">Close</Text>
              </TouchableOpacity>
            </View>

            <View className="p-4">
              {data?.detention ? (
                <View className="bg-slate-50 border border-slate-200 rounded-xl p-3">
                  <Text className="font-extrabold text-red-800">Reason: {data.detention.reason}</Text>
                  <Text className="text-xs text-slate-600 mt-2">
                    {data.detention.task || 'Contact Faculty for task details.'}
                  </Text>
                </View>
              ) : null}

              <Text className="text-[10px] font-extrabold text-slate-500 uppercase mt-4 mb-2">
                Submission Link (Google Drive/PDF)
              </Text>
              <TextInput
                value={submissionUrl}
                onChangeText={setSubmissionUrl}
                autoCapitalize="none"
                placeholder="Paste link here"
                className="w-full px-4 py-3 rounded-xl border border-slate-200 bg-white text-slate-900"
              />

              <TouchableOpacity
                disabled={submitting || !(submissionUrl || '').trim()}
                onPress={onSubmitDetention}
                className={`mt-4 py-3 rounded-xl ${submitting || !(submissionUrl || '').trim() ? 'bg-slate-300' : 'bg-mit-purple'}`}
              >
                <Text className="text-white text-center font-extrabold">
                  {submitting ? 'Submitting…' : 'Submit Task'}
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

function AttendanceRing({ percentage, strokeColor }) {
  const size = 96;
  const strokeWidth = 8;
  const r = 40;
  const cx = 48;
  const cy = 48;
  const circumference = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, Number(percentage) || 0));
  const offset = circumference - (clamped / 100) * circumference;

  return (
    <View className="relative w-24 h-24 items-center justify-center">
      <Svg width={size} height={size} style={{ transform: [{ rotate: '-90deg' }] }}>
        <Circle cx={cx} cy={cy} r={r} stroke="#f3f4f6" strokeWidth={strokeWidth} fill="transparent" />
        <Circle
          cx={cx}
          cy={cy}
          r={r}
          stroke={strokeColor}
          strokeWidth={strokeWidth}
          fill="transparent"
          strokeDasharray={`${circumference} ${circumference}`}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </Svg>
      <Text className="absolute text-xl font-extrabold text-slate-800">{Math.round(clamped)}%</Text>
    </View>
  );
}

function ScoreChip({ label, value }) {
  const v = value === undefined || value === null ? '-' : String(value);
  const isPublished = v !== '-';
  return (
    <View className="items-center flex-1">
      <Text className="text-[10px] font-extrabold text-slate-400 uppercase">{label}</Text>
      <Text className={`mt-1 font-mono font-extrabold ${isPublished ? 'text-blue-700' : 'text-slate-300'}`}>{v}</Text>
    </View>
  );
}
