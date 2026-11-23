import { useState } from "react";
import { Tabs, TabsContent } from "@/components/ui/tabs";
import { AuditAccessTab } from "./AuditAccessTab";
import { AuditDataTab } from "./AuditDataTab";

interface AuditPageProps {
  className?: string;
}

export const AuditPage = ({ className }: AuditPageProps) => {
  const [activeTab, setActiveTab] = useState<"access" | "data">("access");

  return (
    <div className={`w-full max-w-full h-full flex flex-col overflow-hidden ${className}`}>
      <Tabs
        value={activeTab}
        onValueChange={(value) => setActiveTab(value as "access" | "data")}
        className="flex-1 flex flex-col min-h-0"
      >
        <TabsContent
          value="access"
          className="flex-1 min-h-0 mt-0 flex flex-col data-[state=inactive]:hidden"
        >
          {activeTab === "access" && (
            <AuditAccessTab activeTab={activeTab} onTabChange={setActiveTab} />
          )}
        </TabsContent>

        <TabsContent
          value="data"
          className="flex-1 min-h-0 mt-0 flex flex-col data-[state=inactive]:hidden"
        >
          {activeTab === "data" && (
            <AuditDataTab activeTab={activeTab} onTabChange={setActiveTab} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}; 