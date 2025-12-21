import React, { useEffect, useState } from 'react';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';

import { getTimetable } from '../api/ams';
import { useSession } from '../state/session';

export default function TimetableScreen() {
  const { accessToken } = useSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  async function load() {
    setError('');
    try {
      const res = await getTimetable({ token: accessToken });
      setData(res);
    } catch (e) {
      setError(e?.message || 'Failed');
    }
  }

  useEffect(() => {
    load();
  }, []);

  const entries = data?.entries || data?.timetable || [];

  return (
    <ScrollView className="flex-1 bg-mit-slateBg">
      <View className="bg-mit-purple px-5 pt-14 pb-6">
        <Text className="text-white text-2xl font-extrabold">Timetable</Text>
        <Text className="text-white/80 text-xs mt-1">Weekly schedule</Text>
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
          {entries.slice(0, 60).map((e, idx) => (
            <View key={idx} className="py-3 border-b border-slate-100">
              <Text className="text-slate-900 font-bold">
                {e.dayOfWeek || e.day_of_week} {e.startTime || e.start_time}-{e.endTime || e.end_time}
              </Text>
              <Text className="text-slate-500 text-xs mt-1">
                {(e.subject || '').toString()} · {(e.teacher || '').toString()} · {(e.room || '').toString()}
              </Text>
            </View>
          ))}
          {entries.length === 0 ? (
            <Text className="text-slate-500 text-xs">No timetable data</Text>
          ) : null}
        </View>
      </View>
    </ScrollView>
  );
}
