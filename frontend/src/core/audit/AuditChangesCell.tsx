import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const formatAuditValue = (val: any) => {
    if (val === null || val === undefined || val === "") return "пусто";
    if (Array.isArray(val)) {
        if (val.length === 0) return "пусто";
        return val.join(", ");
    }
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
};

export const AuditChangesCell = ({
    changes,
    action
}: {
    changes: Record<string, any>;
    action: string;
}) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const entries = Object.entries(changes);
    const LIMIT = 3;

    const hasMore = entries.length > LIMIT;
    const visibleEntries = isExpanded ? entries : entries.slice(0, LIMIT);

    const renderNewValue = (text: string) => {
        if (text.includes("[Удалено]") || text.includes("[Добавлен]")) {
            const parts = text.split(/(?=\[Добавлен\]|\[Удалено\])/g);
            return parts.map((part, idx) => {
                const trimmed = part.trim();
                if (trimmed.startsWith("[Удалено]")) {
                    return (
                        <div key={idx} className="flex items-start gap-1 mb-1">
                            <Badge variant="destructive" className="text-[9px] px-1 py-0 h-4 mt-0.5 shrink-0">
                                Удалено
                            </Badge>
                            <span className="text-gray-500 break-words">
                                {trimmed.replace("[Удалено]", "").trim()}
                            </span>
                        </div>
                    );
                }
                if (trimmed.startsWith("[Добавлен]")) {
                    return (
                        <div key={idx} className="flex items-start gap-1 mb-1">
                            <Badge variant="default" className="bg-green-600 text-[9px] px-1 py-0 h-4 mt-0.5 shrink-0">
                                Добавлен
                            </Badge>
                            <span className="text-green-700 font-medium break-words">
                                {trimmed.replace("[Добавлен]", "").trim()}
                            </span>
                        </div>
                    );
                }
                return (
                    <div key={idx} className="mb-1 break-words">
                        {trimmed}
                    </div>
                );
            });
        }
        return (
            <span className="text-green-600 font-medium break-words">{text}</span>
        );
    };

    return (
        <div className="space-y-1 text-xs w-full">
            <div className="w-full">
                {visibleEntries.map(([field, val]: [string, any]) => {
                    const oldVal = formatAuditValue(val?.old);
                    const newVal = formatAuditValue(val?.new);

                    const isNewEmpty = newVal === "пусто";
                    const isOldEmpty = oldVal === "пусто";

                    return (
                        <div
                            key={field}
                            className="mb-2 border-b border-gray-100 pb-1 last:border-0 last:pb-0"
                        >
                            <div className="font-semibold text-gray-700 mb-0.5">{field}:</div>
                            <div className="flex flex-col gap-1">
                                {action !== "create" && !isOldEmpty && (
                                    <div className="text-gray-400 text-[10px] mb-1 break-words whitespace-pre-wrap">
                                        {oldVal}
                                    </div>
                                )}
                                {action === "update" ? (
                                    <div className="break-words whitespace-pre-wrap">
                                        {isNewEmpty ? (
                                            <div className="flex items-start gap-1 mb-1">
                                                <Badge variant="destructive" className="text-[9px] px-1 py-0 h-4 mt-0.5 shrink-0">
                                                    Удалено
                                                </Badge>
                                            </div>
                                        ) : (
                                            renderNewValue(newVal)
                                        )}
                                    </div>
                                ) : (
                                    action !== "delete" && !isNewEmpty && (
                                        <div className="break-words whitespace-pre-wrap">
                                            {renderNewValue(newVal)}
                                        </div>
                                    )
                                )}
                            </div>
                        </div>
                    );
                })}
            </div>

            {hasMore && (
                <Button
                    variant="link"
                    size="sm"
                    className="text-xs h-6 px-0 text-blue-600 mt-1 font-semibold"
                    onClick={() => setIsExpanded((v) => !v)}
                >
                    {isExpanded ? "Свернуть" : `Показать все (${entries.length - LIMIT})`}
                </Button>
            )}
        </div>
    );
};