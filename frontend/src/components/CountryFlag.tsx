import React from 'react';

interface CountryFlagProps {
  market: string;
  className?: string;
}

const countryFlagMap: Record<string, string> = {
  // Europe
  'Albania': '🇦🇱',
  'Andorra': '🇦🇩',
  'Austria': '🇦🇹',
  'Belarus': '🇧🇾',
  'Belgium': '🇧🇪',
  'Bosnia and Herzegovina': '🇧🇦',
  'Bulgaria': '🇧🇬',
  'Croatia': '🇭🇷',
  'Cyprus': '🇨🇾',
  'Czechia': '🇨🇿',
  'Denmark': '🇩🇰',
  'Estonia': '🇪🇪',
  'Finland': '🇫🇮',
  'France': '🇫🇷',
  'Germany': '🇩🇪',
  'Greece': '🇬🇷',
  'Hungary': '🇭🇺',
  'Iceland': '🇮🇸',
  'Ireland': '🇮🇪',
  'Italy': '🇮🇹',
  'Kosovo': '🇽🇰',
  'Latvia': '🇱🇻',
  'Liechtenstein': '🇱🇮',
  'Lithuania': '🇱🇹',
  'Luxembourg': '🇱🇺',
  'Malta': '🇲🇹',
  'Moldova': '🇲🇩',
  'Monaco': '🇲🇨',
  'Montenegro': '🇲🇪',
  'Netherlands': '🇳🇱',
  'North Macedonia': '🇲🇰',
  'Norway': '🇳🇴',
  'Poland': '🇵🇱',
  'Portugal': '🇵🇹',
  'Romania': '🇷🇴',
  'Russia': '🇷🇺',
  'San Marino': '🇸🇲',
  'Serbia': '🇷🇸',
  'Slovakia': '🇸🇰',
  'Slovenia': '🇸🇮',
  'Spain': '🇪🇸',
  'Sweden': '🇸🇪',
  'Switzerland': '🇨🇭',
  'Turkey': '🇹🇷',
  'Ukraine': '🇺🇦',
  'United Kingdom': '🇬🇧',
  'Vatican City': '🇻🇦',
  
  // North America
  'Canada': '🇨🇦',
  'USA': '🇺🇸',
  'United States': '🇺🇸',
  'Mexico': '🇲🇽',
  
  // South America
  'Brazil': '🇧🇷',
  
  // Oceania
  'Australia': '🇦🇺',
  'New Zealand': '🇳🇿',
  
  // Common variations
  'UK': '🇬🇧',
  'US': '🇺🇸',
  'United States of America': '🇺🇸',
  'United Kingdom of Great Britain and Northern Ireland': '🇬🇧',
};

export default function CountryFlag({ market, className = "" }: CountryFlagProps) {
  const normalizedMarket = market?.trim();
  const flag = countryFlagMap[normalizedMarket] || '🏳️';
  
  return (
    <span className={`inline-block ${className}`} title={normalizedMarket}>
      {flag}
    </span>
  );
}
