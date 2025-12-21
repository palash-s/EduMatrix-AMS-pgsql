import React, { useEffect, useState } from 'react';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';

import { getAttendance } from '../api/ams';
import { useSession } from '../state/session';

export default function AttendanceScreen() {
  const { accessToken } = useSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  async function load() {
    setError('');
    try {
      const res = await getAttendance({ token: accessToken });
      setData(res);
    } catch (e) {
      setError(e?.message || 'Failed');
    }
  }

  useEffect(() => {
    load();
  }, []);

  const subjects = data?.subjects || [];

  return (
    <ScrollView className="flex-1 bg-mit-slateBg">
      <View className="bg-mit-purple px-5 pt-14 pb-6">
        <Text className="text-white text-2xl font-extrabold">Attendance</Text>
        <Text className="text-white/80 text-xs mt-1">By subject</Text>
        <TouchableOpacity onPress={load} className="mt-4 bg-white/10 px-4 py-2 rounded-xl">
          <Text className="text-white font-bold text-xs">Refresh</Text>
        </TouchableOpacity>
      </View>

      <View className="px-5 -mt-4 pb-10">
        {error ? (
          <View className="bg-red-50 border border-red-100 rounded-2xl p-4 mt-4">
            <Text className="text-red-700 font-bold">{error}</Text>
          </View>
        ) : null}

        <View className="bg-white border border-slate-200 rounded-2xl p-5 mt-4">
          <Text className="text-slate-900 font-extrabold">
            {data?.student_name || data?.studentName || 'Student'}
          </Text>
          <Text className="text-slate-500 text-xs mt-1">
            {data?.student_class || data?.studentClass || ''}
          </Text>

          <View className="mt-4">
            {subjects.slice(0, 40).map((s, idx) => (
              <View key={`${s.code || s.name}-${idx}`} className="py-3 border-b border-slate-100">
                <View className="flex-row justify-between">
                  <Text className="text-slate-900 font-bold">{s.name}</Text>
                  <Text className="text-slate-700 font-extrabold">
                    {Number(s.percentage || 0).toFixed(1)}%
                  </Text>
                </View>
                <Text className="text-slate-500 text-xs mt-1">
                  {s.code} · {s.attended}/{s.conducted}
                </Text>
                <View className="h-2 rounded-full bg-slate-100 mt-2 overflow-hidden">
                  <View
                    className={`h-2 ${Number(s.percentage || 0) >= 75 ? 'bg-mit-teal' : 'bg-red-500'}`}
                    style={{ width: `${Math.max(0, Math.min(100, Number(s.percentage || 0)))}%` }}
                  />
                </View>
              </View>
            ))}
          </View>
        </View>
      </View>
    </ScrollView>
  );
}
