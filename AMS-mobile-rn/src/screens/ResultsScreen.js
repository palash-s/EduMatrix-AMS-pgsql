import React, { useEffect, useState } from 'react';
import { ScrollView, Text, TouchableOpacity, View } from 'react-native';

import { getResults } from '../api/ams';
import { useSession } from '../state/session';

export default function ResultsScreen() {
  const { accessToken } = useSession();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  async function load() {
    setError('');
    try {
      const res = await getResults({ token: accessToken });
      setData(res);
    } catch (e) {
      setError(e?.message || 'Failed');
    }
  }

  useEffect(() => {
    load();
  }, []);

  const rows = data?.results || [];
  const tg = data?.term_grant || data?.termGrant;

  return (
    <ScrollView className="flex-1 bg-mit-slateBg">
      <View className="bg-mit-purple px-5 pt-14 pb-6">
        <Text className="text-white text-2xl font-extrabold">Results</Text>
        <Text className="text-white/80 text-xs mt-1">Marks</Text>
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

        {tg ? (
          <View className="bg-white border border-slate-200 rounded-2xl p-5 mt-4">
            <Text className="text-mit-purple font-extrabold">Term Grant</Text>
            <Text className="text-slate-900 font-extrabold text-lg mt-2">{tg.status}</Text>
            {tg.remarks ? (
              <Text className="text-slate-500 text-xs mt-1">{tg.remarks}</Text>
            ) : null}
          </View>
        ) : null}

        <View className="bg-white border border-slate-200 rounded-2xl p-5 mt-4">
          <Text className="text-mit-purple font-extrabold">Subjects</Text>
          {rows.length === 0 ? (
            <Text className="text-slate-500 text-xs mt-3">No results</Text>
          ) : (
            <View className="mt-3">
              {rows.slice(0, 40).map((r, idx) => (
                <View key={`${r.code}-${idx}`} className="py-3 border-b border-slate-100">
                  <Text className="text-slate-900 font-bold">
                    {r.subject} ({r.code})
                  </Text>
                  <Text className="text-slate-500 text-xs mt-1">
                    TA1: {r.ta1} · TA2: {r.ta2} · TA3: {r.ta3}
                  </Text>
                </View>
              ))}
            </View>
          )}
        </View>
      </View>
    </ScrollView>
  );
}
