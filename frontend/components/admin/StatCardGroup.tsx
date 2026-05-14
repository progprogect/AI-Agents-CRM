/** Grouped stat cards component. */

import React from "react";
import { StatCard } from "./StatCard";

interface StatCardGroupProps {
  title: string;
  cards: Array<{
    label: string;
    value: number;
    change?: number;
    icon?: string;
    colorClass?: string;
    href?: string;
  }>;
  columns?: number;
}

export const StatCardGroup: React.FC<StatCardGroupProps> = ({
  title,
  cards,
  columns = 5,
}) => {
  const gridCols = {
    1: "grid-cols-1",
    2: "grid-cols-1 md:grid-cols-2",
    3: "grid-cols-1 md:grid-cols-2 lg:grid-cols-3",
    4: "grid-cols-1 md:grid-cols-2 lg:grid-cols-4",
    5: "grid-cols-1 md:grid-cols-2 lg:grid-cols-5",
  };

  return (
    <div className="mb-8">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">{title}</h2>
      <div className={`grid ${gridCols[columns as keyof typeof gridCols] || gridCols[5]} gap-4`}>
        {cards.map((card) => (
          <StatCard key={card.label} {...card} />
        ))}
      </div>
    </div>
  );
};
